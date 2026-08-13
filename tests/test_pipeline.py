from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication

from captions.app import CaptionApplication
from captions.audio_asr import AudioAsrWorker
from captions.config import AppConfig
from captions.core.diagnostics import Diagnostics
from captions.ports.audio_source import AudioCaptureKind
from captions.segmenter import Segmenter
from captions.translation import Translator
from captions.translation_session import TranslationSession
from captions.ui.caption_canvas import CaptionCanvas
from captions.ui.history_dialog import HistoryDialog


class PipelineApp:
    pass


def pipeline_app(config: AppConfig, translation_session) -> PipelineApp:
    app = PipelineApp()
    app.closing = False
    app.config = config
    app.diagnostics = Diagnostics()
    app.segmenter = Segmenter(
            max_chars=config.segmentation.max_chars,
            max_seconds=config.segmentation.max_seconds,
            split_lookback_chars=config.segmentation.split_lookback_chars,
            split_lookahead_chars=config.segmentation.split_lookahead_chars,
    )
    app.translation_session = translation_session
    app.history = HistoryDialog()
    app.active_cue_id = 1
    app.display_generation = 0
    app.display_kind = ""
    app.overlay = SimpleNamespace(canvas=CaptionCanvas(config.subtitle))
    app._restart_clear_timer = lambda: None
    app._set_status = lambda text: None
    app.history.set_translation_enabled(config.translation.enabled)
    for name in (
        "_asr_partial",
        "_asr_endpoint",
        "_commit",
        "_display_source",
        "_display_translation",
        "_translation_started",
        "_translation_progress",
        "_translation_result",
        "_translation_error",
        "_translation_cancelled",
        "_translation_previews_discarded",
    ):
        setattr(app, name, MethodType(getattr(CaptionApplication, name), app))
    return app


class PipelineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_audio_to_history_chain_commits_each_recognizer_endpoint_once(self) -> None:
        config = AppConfig()
        config.translation.enabled = False
        translations = SimpleNamespace(
            schedule_preview=lambda *args: self.fail("translation is disabled"),
            request_commit=lambda *args, **kwargs: self.fail("translation is disabled"),
        )
        app = pipeline_app(config, translations)
        updates = iter(
            (
                SimpleNamespace(text="First", endpoint=False),
                SimpleNamespace(text="First sentence.", endpoint=True),
                SimpleNamespace(text="Second", endpoint=False),
                SimpleNamespace(text="Second sentence.", endpoint=True),
            )
        )

        class Recognition:
            def accept(inner_self, samples):
                update = next(updates)
                if update.text == "Second sentence.":
                    worker.stop()
                return update

            def reset(inner_self) -> None:
                pass

        class SpeechGate:
            def __init__(inner_self, vad) -> None:
                pass

            def process(inner_self, samples):
                return [(samples, False)]

            def reset(inner_self) -> None:
                pass

        class Capture:
            name = "synthetic-output"

            def __enter__(inner_self):
                return inner_self

            def __exit__(inner_self, *args) -> None:
                pass

            def read(inner_self, frames):
                return np.zeros((frames, 1), dtype=np.float32)

        worker = AudioAsrWorker(
            config,
            audio_source=SimpleNamespace(
                capture_kind=AudioCaptureKind.SYSTEM_OUTPUT,
                open_default=lambda **kwargs: Capture(),
            ),
            recognition_backend=SimpleNamespace(
                create_streaming=lambda current: Recognition(),
                create_vad=lambda current: object(),
            ),
        )
        worker.partial.connect(app._asr_partial)
        worker.endpoint.connect(app._asr_endpoint)

        with patch("captions.audio_asr.VadSpeechGate", SpeechGate):
            worker.run()

        self.assertEqual(
            [record.source for record in app.history.records],
            ["First sentence.", "Second sentence."],
        )
        self.assertTrue(all(record.backend == "off" for record in app.history.records))
        app.history.close()

    def test_continuous_speech_stress_preserves_the_complete_source_stream(self) -> None:
        config = AppConfig()
        config.translation.enabled = False
        config.segmentation.max_chars = 40
        config.segmentation.split_lookback_chars = 10
        config.segmentation.split_lookahead_chars = 20
        translations = SimpleNamespace(
            schedule_preview=lambda *args: self.fail("translation is disabled"),
            request_commit=lambda *args, **kwargs: self.fail("translation is disabled"),
        )
        app = pipeline_app(config, translations)
        words = [f"word{index}" for index in range(1500)]

        for revision in range(1, len(words) + 1):
            app._asr_partial(" ".join(words[:revision]), revision)
        app._asr_endpoint()

        reconstructed = " ".join(record.source for record in app.history.records)
        self.assertEqual(reconstructed, " ".join(words))
        self.assertGreater(len(app.history.records), 100)
        app.history.close()

    def test_translation_pressure_never_writes_a_result_to_the_wrong_record(self) -> None:
        config = AppConfig()
        config.translation.enabled = True
        config.translation.timeout_ms = 120000
        session = TranslationSession()
        app = pipeline_app(config, session)
        session.started.connect(app._translation_started)
        session.progress.connect(app._translation_progress)
        session.result.connect(app._translation_result)
        session.error.connect(app._translation_error)
        session.cancelled.connect(app._translation_cancelled)
        session.previews_discarded.connect(app._translation_previews_discarded)

        def translate(text, history, current, progress, **kwargs):
            time.sleep(0.002)
            return f"translated:{text}"

        session.translator._request = translate
        for index in range(200):
            app._commit(f"source-{index}", False)

        deadline = time.monotonic() + 5
        while session.jobs and time.monotonic() < deadline:
            self.qt_app.processEvents()
            time.sleep(0.002)

        for record in app.history.records:
            if record.translation:
                self.assertEqual(record.translation, f"translated:{record.source}")
        self.assertLessEqual(
            sum(not future.done() for future in session.translator._final_futures),
            32,
        )
        self.assertFalse(session.jobs)
        session.close()
        deadline = time.monotonic() + 3
        while session.shutting_down and time.monotonic() < deadline:
            self.qt_app.processEvents()
            time.sleep(0.005)
        app.history.close()


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_debug_trace_is_disabled_by_default_and_structured_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions-debug.jsonl"
            diagnostics = Diagnostics(False, path)
            diagnostics.event("asr.partial", revision=1, text="hello")
            self.assertFalse(path.exists())

            diagnostics.configure(True)
            diagnostics.event("segment.committed", cue_id=3, source="hello")
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["event"], "segment.committed")
        self.assertEqual(payload["cue_id"], 3)
        self.assertEqual(payload["source"], "hello")
        self.assertIn("session", payload)
        self.assertIn("elapsed_ms", payload)

    def test_translation_job_is_registered_before_worker_execution(self) -> None:
        registered: list[int] = []

        def request(text, history, config, progress, **kwargs):
            self.assertEqual(registered, [1])
            return "done"

        with patch.object(Translator, "_request", staticmethod(request)):
            translator = Translator()
            translator.translate(
                "source",
                [],
                AppConfig().translation,
                on_registered=registered.append,
            )
            translator.wait_closed()

    def test_translation_trace_correlates_the_complete_job_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions-debug.jsonl"
            session = TranslationSession(diagnostics=Diagnostics(True, path))

            def translate(text, history, config, progress, **kwargs):
                progress("partial")
                return "complete"

            session.translator._request = translate
            session.request_commit(
                "source",
                [],
                AppConfig().translation,
                record_id=41,
                cue_id=7,
            )
            deadline = time.monotonic() + 2
            while session.jobs and time.monotonic() < deadline:
                self.qt_app.processEvents()
                time.sleep(0.002)
            events = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            session.close()
            deadline = time.monotonic() + 2
            while session.shutting_down and time.monotonic() < deadline:
                self.qt_app.processEvents()
                time.sleep(0.002)

        self.assertEqual(
            [event["event"] for event in events],
            [
                "translation.submitted",
                "translation.started",
                "translation.first_progress",
                "translation.completed",
            ],
        )
        self.assertEqual(len({event["generation"] for event in events}), 1)
        self.assertTrue(all(event["cue_id"] == 7 for event in events))
        self.assertTrue(all(event["record_id"] == 41 for event in events))


if __name__ == "__main__":
    unittest.main()
