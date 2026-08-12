from __future__ import annotations

import tempfile
import threading
import time
import unittest
import os
import io
import hashlib
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPalette, QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea

from captions.app import CaptionApplication, TranslationJob
from captions.audio_asr import AudioAsrWorker, AutoStandbyDetector, VadSpeechGate
from captions.config import (
    AppConfig,
    CHINESE_MODEL_NAME,
    MULTILINGUAL_MODEL_NAME,
    NEMOTRON_MULTILINGUAL_LANGUAGES,
    MODEL_CATALOG,
    apply_model_preset,
    default_model_dir,
    load_config,
    model_download_integrity,
    model_download_spec,
    model_is_complete,
    save_config,
)
from captions.model_download import ModelDownloadWorker
from captions.segmenter import Segmenter
from captions.translation import (
    HistoryRecord,
    MAX_PENDING_FINAL_TRANSLATIONS,
    Translator,
    build_hymt_prompt,
    matching_glossary,
    translation_queue_expired,
)
from captions.translation_session import TranslationSession
from captions.ui.caption_canvas import CaptionCanvas
from captions.ui.history_dialog import (
    HISTORY_PAGE_SIZE,
    MAX_HISTORY_RECORDS,
    HistoryDialog,
)
from captions.ui.settings_dialog import SettingsDialog


class SegmenterTests(unittest.TestCase):
    def test_terminal_punctuation_requires_a_followup_update(self) -> None:
        segmenter = Segmenter()
        first = segmenter.update("Hello world.", now=1)
        second = segmenter.update("Hello world.", now=1.56)
        self.assertFalse(first.committed)
        self.assertEqual(second.committed, "Hello world.")

    def test_following_text_is_retained(self) -> None:
        segmenter = Segmenter()
        segmenter.update("One.", now=1)
        update = segmenter.update("One. Two", now=1.56)
        self.assertEqual(update.committed, "One.")
        self.assertEqual(update.active, "Two")

    def test_long_text_is_forced_at_a_word_boundary(self) -> None:
        segmenter = Segmenter(
            max_chars=20, split_lookback_chars=4, split_lookahead_chars=5
        )
        update = segmenter.update("one two three four five six", now=1)
        self.assertTrue(update.forced)
        self.assertTrue(update.committed)
        self.assertFalse(update.committed.endswith(" f"))

    def test_repeated_text_never_moves_the_consumed_position_backwards(self) -> None:
        segmenter = Segmenter(
            max_chars=24, split_lookback_chars=4, split_lookahead_chars=8
        )
        text = "repeat this phrase " * 8
        segmenter.update(text, now=1)
        lengths = [len(segmenter.active)]
        hard_limit = (
            segmenter.max_chars + segmenter.split_lookahead_chars
        )
        while len(segmenter.active) >= hard_limit:
            segmenter.update(text, now=1)
            lengths.append(len(segmenter.active))
        self.assertEqual(lengths, sorted(lengths, reverse=True))

    def test_soft_limit_waits_for_forward_punctuation(self) -> None:
        segmenter = Segmenter(
            max_chars=20, split_lookback_chars=4, split_lookahead_chars=20
        )
        waiting = segmenter.update("one two three four five six", now=1)
        committed = segmenter.update("one two three four five six seven.", now=2)

        self.assertFalse(waiting.committed)
        self.assertEqual(committed.committed, "one two three four five six seven.")
        self.assertFalse(committed.forced)

    def test_time_limit_commits_the_whole_active_text(self) -> None:
        segmenter = Segmenter(max_chars=240, max_seconds=10)
        segmenter.update("one sentence is still being spoken", now=1)
        update = segmenter.update(
            "one sentence is still being spoken very slowly", now=11
        )

        self.assertEqual(
            update.committed, "one sentence is still being spoken very slowly"
        )
        self.assertEqual(update.active, "")


class TranslationTests(unittest.TestCase):
    def test_glossary_is_case_insensitive_and_word_bounded(self) -> None:
        terms = {"Vault": "避难所", "Brotherhood of Steel": "钢铁兄弟会"}
        self.assertEqual(matching_glossary(terms, "Enter the VAULT."), [("Vault", "避难所")])
        self.assertEqual(matching_glossary(terms, "The door is vaulted."), [])

    def test_prompt_only_includes_matching_terms(self) -> None:
        config = AppConfig().translation
        config.glossary = {"Vault": "避难所", "Laser Rifle": "激光步枪"}
        prompt = build_hymt_prompt("Enter the vault.", [], config)
        self.assertIn("Vault = 避难所", prompt)
        self.assertNotIn("Laser Rifle", prompt)

    def test_prompt_uses_the_selected_language_direction(self) -> None:
        config = AppConfig().translation
        config.source_lang = "JA"
        config.target_lang = "EN-US"

        prompt = build_hymt_prompt("こんにちは", [], config)

        self.assertIn("日语字幕翻译成英语", prompt)
        self.assertNotIn("英文字幕翻译成简体中文", prompt)

    def test_deepl_uses_the_selected_service_and_header_authentication(self) -> None:
        config = AppConfig().translation
        config.backend = "deepl"
        config.deepl_api_key = "secret"
        config.deepl_api_plan = "free"
        config.source_lang = "EN"
        config.target_lang = "ZH-HANS"
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"translations": [{"text": "测试译文"}]},
        )

        with patch("captions.translation.httpx.post", return_value=response) as post:
            translated = Translator._request("Test", [], config, lambda text: None)

        self.assertEqual(translated, "测试译文")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api-free.deepl.com/v2/translate")
        self.assertEqual(kwargs["headers"]["Authorization"], "DeepL-Auth-Key secret")
        self.assertEqual(
            kwargs["json"],
            {"text": ["Test"], "target_lang": "ZH-HANS", "source_lang": "EN"},
        )

    def test_google2_uses_the_selected_language_direction(self) -> None:
        config = AppConfig().translation
        config.backend = "google2"
        config.source_lang = "JA"
        config.target_lang = "EN-US"
        config.google2_api_key = "editable-google2-key"
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [["Hello"]],
        )

        with patch("captions.translation.httpx.post", return_value=response) as post:
            translated = Translator._request("こんにちは", [], config, lambda text: None)

        self.assertEqual(translated, "Hello")
        self.assertEqual(post.call_args.kwargs["json"], [[["こんにちは"], "ja", "en"], "wt_lib"])
        self.assertEqual(
            post.call_args.kwargs["headers"]["X-Goog-API-Key"],
            "editable-google2-key",
        )

    def test_google2_fetches_a_key_when_configuration_is_empty(self) -> None:
        config = AppConfig().translation
        config.google2_api_key = ""
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [["测试译文"]],
        )
        client = Mock()
        client.post.return_value = response
        with patch.object(
            Translator,
            "acquire_google2_api_key",
            return_value="fetched-google2-key",
        ):
            translated = Translator._google2(
                "Test",
                config,
                15.0,
                client=client,
            )

        self.assertEqual(translated, "测试译文")
        self.assertEqual(config.google2_api_key, "fetched-google2-key")
        self.assertEqual(
            client.post.call_args.kwargs["headers"]["X-Goog-API-Key"],
            "fetched-google2-key",
        )

    def test_google2_key_is_extracted_from_current_component_script(self) -> None:
        key = "AIza" + "a" * 35
        bootstrap = SimpleNamespace(
            text=(
                "_loadJs('https:\\/\\/translate.googleapis.com\\/_\\/"
                "translate_http\\/_\\/js\\/k\\x3dversion\\/m\\x3del_main')"
            ),
            raise_for_status=lambda: None,
        )
        main_script = SimpleNamespace(
            text=(
                'path:"/v1/translateHtml",method:"POST",headers:'
                '{"X-goog-api-key":"' + key + '"}'
            ),
            raise_for_status=lambda: None,
        )
        client = Mock()
        client.get.side_effect = [bootstrap, main_script]

        self.assertEqual(
            Translator.acquire_google2_api_key(client=client),
            key,
        )
        self.assertEqual(client.get.call_count, 2)

    def test_deepl_requires_a_key(self) -> None:
        config = AppConfig().translation
        config.deepl_api_key = ""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DeepL API 密钥"):
                Translator._deepl("Test", config, 15.0)


    def test_preview_queue_keeps_current_and_coalesces_waiting_requests(self) -> None:
        started = threading.Event()
        release = threading.Event()
        calls: list[str] = []

        def fake_request(text, history, config, progress, **kwargs):
            calls.append(text)
            if text == "first":
                started.set()
                release.wait(2)
            return text

        with patch.object(Translator, "_request", staticmethod(fake_request)):
            translator = Translator()
            translator.translate("first", [], AppConfig().translation, preview=True)
            self.assertTrue(started.wait(1))
            translator.translate("middle", [], AppConfig().translation, preview=True)
            translator.translate("latest", [], AppConfig().translation, preview=True)
            release.set()
            deadline = time.monotonic() + 2
            while translator._futures and time.monotonic() < deadline:
                time.sleep(0.01)
            translator.close()

        self.assertEqual(calls, ["first", "latest"])

    def test_final_queue_is_bounded_when_the_backend_stalls(self) -> None:
        started = threading.Event()
        release = threading.Event()
        errors: list[str] = []

        def fake_request(text, history, config, progress, **kwargs):
            started.set()
            release.wait(2)
            return text

        with patch.object(Translator, "_request", staticmethod(fake_request)):
            translator = Translator()
            translator.signals.error.connect(
                lambda generation, message: errors.append(message)
            )
            translator.translate("first", [], AppConfig().translation)
            self.assertTrue(started.wait(1))
            for index in range(MAX_PENDING_FINAL_TRANSLATIONS + 20):
                translator.translate(f"queued-{index}", [], AppConfig().translation)

            self.assertLessEqual(
                len(translator._futures), MAX_PENDING_FINAL_TRANSLATIONS
            )
            self.assertTrue(any("积压过多" in message for message in errors))
            release.set()
            deadline = time.monotonic() + 2
            while translator._futures and time.monotonic() < deadline:
                time.sleep(0.01)
            translator.close()

        self.assertEqual(translator._futures, set())

    def test_translation_task_only_keeps_configured_history(self) -> None:
        received_lengths: list[int] = []

        def fake_request(text, history, config, progress, **kwargs):
            received_lengths.append(len(history))
            return text

        config = AppConfig().translation
        config.context_segments = 3
        history = [
            HistoryRecord("12:00:00", f"source-{index}", "", "test")
            for index in range(100)
        ]
        with patch.object(Translator, "_request", staticmethod(fake_request)):
            translator = Translator()
            translator.translate("current", history, config)
            deadline = time.monotonic() + 2
            while translator._futures and time.monotonic() < deadline:
                time.sleep(0.01)
            translator.close()

        self.assertEqual(received_lengths, [3])

    def test_final_translation_expires_after_the_configured_queue_age(self) -> None:
        self.assertFalse(translation_queue_expired(10.0, 15000, now=24.9))
        self.assertTrue(translation_queue_expired(10.0, 15000, now=25.1))

    def test_streaming_response_has_a_hard_character_limit(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def raise_for_status(self):
                return None

            def iter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"abcd"}}]}'

        with (
            patch("captions.translation.httpx.stream", return_value=FakeResponse()),
            patch("captions.translation.MAX_STREAM_RESPONSE_CHARS", 3),
        ):
            with self.assertRaisesRegex(RuntimeError, "响应过长"):
                Translator._llama_stream(
                    "http://localhost", {}, 15.0, lambda partial: None
                )

    def test_streaming_response_has_a_total_deadline(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def raise_for_status(self):
                return None

            def iter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"a"}}]}'

        with (
            patch("captions.translation.httpx.stream", return_value=FakeResponse()),
            patch("captions.translation.time.monotonic", side_effect=[0.0, 2.0]),
        ):
            with self.assertRaisesRegex(TimeoutError, "超过总时限"):
                Translator._llama_stream(
                    "http://localhost", {}, 1.0, lambda partial: None
                )

    def test_current_preview_progress_is_not_hidden_by_a_newer_queued_job(self) -> None:
        updates: list[str] = []
        canvas = SimpleNamespace(
            set_content=lambda **values: updates.append(values["translation"])
        )
        job = TranslationJob("preview", None, "first", 1)
        app = SimpleNamespace(
            display_generation=1,
            overlay=SimpleNamespace(canvas=canvas),
            _display_translation=lambda job, text: updates.append(text),
            history=SimpleNamespace(
                live_source="first",
                set_live=lambda **values: None,
                set_live_translation=lambda source, text: None,
            ),
        )

        CaptionApplication._translation_progress(app, 1, job, "visible token")

        self.assertEqual(updates, ["visible token"])

    def test_late_commit_result_updates_history_but_not_a_newer_caption(self) -> None:
        canvas_updates: list[dict] = []
        history_updates: list[tuple[int, str]] = []
        job = TranslationJob("commit", 4, "old sentence", 1)
        app = SimpleNamespace(
            display_generation=2,
            display_kind="preview",
            history=SimpleNamespace(
                update_translation=lambda index, text: history_updates.append(
                    (index, text)
                )
            ),
            overlay=SimpleNamespace(
                canvas=SimpleNamespace(
                    set_content=lambda **values: canvas_updates.append(values)
                )
            ),
            _restart_clear_timer=lambda: None,
            _display_translation=lambda job, text, final=False: canvas_updates.append(
                {"source": job.source, "translation": text}
            ),
        )

        CaptionApplication._translation_result(app, 1, job, "old translation")

        self.assertEqual(history_updates, [(4, "old translation")])
        self.assertEqual(canvas_updates, [])

    def test_active_sentence_defers_the_clear_timer(self) -> None:
        events: list[str] = []
        app = SimpleNamespace(
            segmenter=SimpleNamespace(active="still speaking"),
            display_generation=0,
            display_kind="preview",
            translation_session=SimpleNamespace(has_job=lambda generation: False),
            _restart_clear_timer=lambda: events.append("deferred"),
            overlay=SimpleNamespace(
                canvas=SimpleNamespace(clear=lambda: events.append("cleared"))
            ),
        )

        CaptionApplication._clear_if_idle(app)

        self.assertEqual(events, ["deferred"])


class TranslationSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_preview_scheduling_uses_segmentation_settings(self) -> None:
        session = TranslationSession()
        config = AppConfig()
        config.segmentation.preview_min_chars = 4
        calls: list[tuple[str, bool]] = []

        def translate(text, history, translation, *, preview=False):
            calls.append((text, preview))
            return 1

        session.translator.translate = translate
        session.schedule_preview(
            "test",
            [],
            config.translation,
            config.segmentation,
            cue_id=7,
        )

        self.assertEqual(calls, [("test", True)])
        self.assertEqual(session.jobs[1], TranslationJob("preview", None, "test", 7))
        session.close()

    def test_commit_discards_preview_state_without_changing_text(self) -> None:
        session = TranslationSession()
        config = AppConfig()
        session.translator.translate = lambda *args, **kwargs: 2
        session.translator.cancel_pending = lambda: None
        session.jobs[1] = TranslationJob("preview", None, "unchanged", 3)
        discarded: list[bool] = []
        session.previews_discarded.connect(lambda: discarded.append(True))

        generation = session.request_commit(
            "unchanged",
            [],
            config.translation,
            record_id=9,
            cue_id=3,
        )

        self.assertEqual(generation, 2)
        self.assertNotIn(1, session.jobs)
        self.assertEqual(session.jobs[2], TranslationJob("commit", 9, "unchanged", 3))
        self.assertEqual(discarded, [True])
        session.close()


class CaptureLifecycleTests(unittest.TestCase):
    def test_pause_keeps_the_worker_and_loaded_model_alive(self) -> None:
        events: list[str] = []
        app = SimpleNamespace(
            capture_session=SimpleNamespace(
                running=True,
                pause=lambda: events.append("paused"),
                stop=lambda: events.append("stopped"),
            ),
            capturing=True,
            capture_paused=False,
            model_loaded=True,
            segmenter=SimpleNamespace(
                flush=lambda forced=True: SimpleNamespace(committed="")
            ),
            overlay=SimpleNamespace(
                set_capturing=lambda value: events.append(f"overlay:{value}")
            ),
            capture_action=SimpleNamespace(
                setText=lambda text: events.append(f"action:{text}")
            ),
            _set_status=lambda text: events.append(f"status:{text}"),
            _set_model_status=lambda text: events.append(f"model:{text}"),
        )

        CaptionApplication.stop_capture(app)

        self.assertIn("paused", events)
        self.assertNotIn("stopped", events)
        self.assertFalse(app.capturing)
        self.assertTrue(app.capture_paused)
        self.assertIn("model:已加载", events)

    def test_resume_reuses_the_existing_worker(self) -> None:
        events: list[str] = []
        app = SimpleNamespace(
            capture_session=SimpleNamespace(
                running=True,
                resume=lambda: events.append("resumed"),
            ),
            capture_paused=True,
            capturing=False,
            overlay=SimpleNamespace(
                set_capturing=lambda value: events.append(f"overlay:{value}")
            ),
            capture_action=SimpleNamespace(
                setText=lambda text: events.append(f"action:{text}")
            ),
            _set_status=lambda text: events.append(f"status:{text}"),
        )

        CaptionApplication.start_capture(app)

        self.assertEqual(events[0], "resumed")
        self.assertTrue(app.capturing)
        self.assertFalse(app.capture_paused)


class AudioAsrTests(unittest.TestCase):
    def test_auto_standby_enters_after_silence_and_wakes_on_audio(self) -> None:
        detector = AutoStandbyDetector(30, now=10.0)

        self.assertIsNone(detector.update(0.0, now=39.9))
        self.assertIs(detector.update(0.0, now=40.0), True)
        self.assertTrue(detector.standby)
        self.assertIs(detector.update(0.01, now=41.0), False)
        self.assertFalse(detector.standby)

    def test_disabling_auto_standby_wakes_the_detector(self) -> None:
        detector = AutoStandbyDetector(1, now=1.0)
        detector.update(0.0, now=2.0)
        self.assertTrue(detector.configure(0, now=3.0))
        self.assertFalse(detector.standby)

    def test_multilingual_stream_receives_the_selected_language(self) -> None:
        config = AppConfig()
        config.asr.model_variant = "multilingual"
        config.asr.language = "ja"
        options: list[tuple[str, str]] = []
        stream = SimpleNamespace(
            set_option=lambda key, value: options.append((key, value))
        )
        recognizer = SimpleNamespace(create_stream=lambda: stream)

        created = AudioAsrWorker(config)._create_stream(recognizer)

        self.assertIs(created, stream)
        self.assertEqual(options, [("language", "ja")])

    def test_single_language_stream_does_not_receive_a_language_option(self) -> None:
        config = AppConfig()
        options: list[tuple[str, str]] = []
        stream = SimpleNamespace(set_option=lambda key, value: options.append((key, value)))
        recognizer = SimpleNamespace(create_stream=lambda: stream)

        AudioAsrWorker(config)._create_stream(recognizer)

        self.assertEqual(options, [])

    def test_vad_gate_keeps_preroll_and_marks_the_speech_endpoint(self) -> None:
        class FakeVad:
            def __init__(self) -> None:
                self.states = iter((False, False, True, True, False))
                self.detected = False

            def accept_waveform(self, samples) -> None:
                self.detected = next(self.states)

            def is_speech_detected(self) -> bool:
                return self.detected

            def empty(self) -> bool:
                return True

            def pop(self) -> None:
                raise AssertionError("nothing to pop")

            def reset(self) -> None:
                self.detected = False

        gate = VadSpeechGate(FakeVad(), window_size=4)
        samples = np.arange(20, dtype=np.float32)

        events = gate.process(samples)

        self.assertEqual([len(chunk) for chunk, _ in events], [12, 4, 4])
        self.assertEqual([endpoint for _, endpoint in events], [False, False, True])
        np.testing.assert_array_equal(events[0][0], samples[:12])

    def test_bundled_silero_vad_ignores_digital_silence(self) -> None:
        gate = VadSpeechGate(AudioAsrWorker._create_vad())
        events = gate.process(np.zeros(16000, dtype=np.float32))
        self.assertEqual(events, [])


class CaptionCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def _logical_lines(self, rows: int) -> list[tuple[str, str]]:
        style = AppConfig().subtitle
        style.max_rows = rows
        canvas = CaptionCanvas(style)
        canvas.set_cue(1, "oldest en", "旧一")
        canvas.set_cue(2, "previous en", "旧二")
        canvas.set_cue(3, "current en", "当前")
        return [(line.text, line.kind) for line in canvas._visible_lines(2000)]

    def test_bilingual_row_budget_keeps_the_current_pair(self) -> None:
        self.assertEqual(
            self._logical_lines(2),
            [("current en", "source"), ("当前", "translation")],
        )

    def test_three_rows_adds_the_previous_translation(self) -> None:
        self.assertEqual(
            self._logical_lines(3),
            [
                ("旧二", "translation"),
                ("current en", "source"),
                ("当前", "translation"),
            ],
        )

    def test_six_rows_adds_two_previous_pairs(self) -> None:
        self.assertEqual(
            self._logical_lines(6),
            [
                ("oldest en", "source"),
                ("旧一", "translation"),
                ("previous en", "source"),
                ("旧二", "translation"),
                ("current en", "source"),
                ("当前", "translation"),
            ],
        )

    def test_streaming_waits_until_the_new_text_is_longer(self) -> None:
        canvas = SimpleNamespace(cue_id=1, translation="旧译文")
        updates: list[tuple[int, str, str]] = []
        canvas.set_cue = lambda cue_id, source, translation: updates.append(
            (cue_id, source, translation)
        )
        app = SimpleNamespace(overlay=SimpleNamespace(canvas=canvas))
        job = TranslationJob("preview", None, "source", 1)

        CaptionApplication._display_translation(app, job, "新译")
        CaptionApplication._display_translation(app, job, "新的译文更长")

        self.assertEqual(updates, [(1, "source", "新的译文更长")])

    def test_preview_visibly_distinguishes_all_background_modes(self) -> None:
        def dark_pixels(background: str) -> int:
            style = AppConfig().subtitle
            style.background = background
            style.background_color = "rgba(0,0,0,1)"
            style.shadow = False
            style.outline_width = 0
            canvas = CaptionCanvas(style, preview=True)
            canvas.resize(640, 220)
            canvas.set_cue(1, "Short source", "这是一条明显更长的字幕块预览文本")
            canvas.show()
            self.qt_app.processEvents()
            image = canvas.grab().toImage()
            canvas.close()
            return sum(
                1
                for y in range(image.height())
                for x in range(image.width())
                if image.pixelColor(x, y).lightness() < 40
            )

        none = dark_pixels("none")
        line = dark_pixels("line")
        block = dark_pixels("block")
        self.assertGreater(line, none + 1000)
        self.assertGreater(block, line + 1000)

    def test_physical_wrapped_lines_respect_the_display_budget(self) -> None:
        style = AppConfig().subtitle
        style.mode = "source"
        style.max_rows = 2
        canvas = CaptionCanvas(style)
        canvas.resize(420, 220)
        canvas.set_cue(
            1,
            "This is a deliberately long subtitle that wraps naturally across "
            "several physical lines in a narrow caption window.",
            "",
        )

        lines = canvas._visible_lines(380)

        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.kind == "source" for line in lines))

    def test_caption_size_setting_is_measured_in_points(self) -> None:
        style = AppConfig().subtitle
        style.source_size = 30
        style.translation_size = 32
        canvas = CaptionCanvas(style)

        self.assertEqual(canvas._font("source").pointSize(), 30)
        self.assertEqual(canvas._font("translation").pointSize(), 32)


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_model_control_switches_between_download_and_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = AppConfig()
            config.asr.model_dir = directory
            dialog = SettingsDialog(config)
            self.assertTrue(dialog.model_status.isEnabled())
            self.assertIn("下载", dialog.model_status.text())

            for name in ("encoder", "decoder", "joiner", "tokens"):
                (Path(directory) / getattr(config.asr, name)).write_bytes(b"x")
            dialog._refresh_model_path_status()

            self.assertFalse(dialog.model_status.isEnabled())
            self.assertIn("已就绪", dialog.model_status.text())
            dialog.close()

    def test_settings_are_separated_into_clear_sections(self) -> None:
        dialog = SettingsDialog(AppConfig())
        self.assertEqual(
            [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())],
            ["识别", "翻译", "外观", "术语表"],
        )
        self.assertEqual(dialog.backend.currentData(), "llama")
        self.assertEqual(dialog.asr_language.count(), 1)
        self.assertEqual(dialog.asr_language.currentData(), "en")
        self.assertEqual(dialog.source_lang.itemData(0), "AUTO")
        self.assertEqual(dialog.source_lang.itemText(0), "自动检测")
        self.assertEqual(dialog.source_lang.currentData(), "EN")
        self.assertEqual(dialog.target_lang.currentData(), "ZH-HANS")
        self.assertFalse(dialog.asr_language.isEnabled())
        self.assertTrue(dialog.recognition_advanced.body.isHidden())
        self.assertTrue(dialog.translation_advanced.body.isHidden())
        dialog.close()

    def test_settings_wheel_controls_only_scroll_the_page(self) -> None:
        dialog = SettingsDialog(AppConfig())
        dialog.tabs.setCurrentIndex(2)
        dialog.show()
        self.qt_app.processEvents()
        scroll = dialog.source_size.parentWidget()
        while scroll is not None and not isinstance(scroll, QScrollArea):
            scroll = scroll.parentWidget()
        scrollbar = scroll.verticalScrollBar()
        before_value = dialog.source_size.value()
        dialog.background_color.setFocus()
        self.qt_app.processEvents()
        before_focus = self.qt_app.focusWidget()
        event = QWheelEvent(
            QPointF(4, 4), QPointF(4, 4), QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )

        self.qt_app.sendEvent(dialog.source_size, event)
        self.qt_app.processEvents()

        self.assertEqual(dialog.source_size.value(), before_value)
        self.assertGreater(scrollbar.value(), 0)
        self.assertIs(self.qt_app.focusWidget(), before_focus)
        for control in (
            dialog.source_size,
            dialog.outline_width,
            dialog.mode,
            dialog.font,
        ):
            self.assertEqual(control.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        dialog.close()

    def test_multilingual_selection_uses_its_default_directory(self) -> None:
        dialog = SettingsDialog(AppConfig())
        dialog.model_variant.setCurrentIndex(
            dialog.model_variant.findData("multilingual")
        )

        self.assertTrue(dialog.asr_language.isEnabled())
        self.assertEqual(dialog.asr_language.currentData(), "auto")
        self.assertEqual(
            [
                dialog.asr_language.itemData(index)
                for index in range(dialog.asr_language.count())
            ],
            ["auto", *NEMOTRON_MULTILINGUAL_LANGUAGES],
        )
        self.assertEqual(dialog.model_dir.text(), default_model_dir("multilingual"))
        self.assertIn(MULTILINGUAL_MODEL_NAME, dialog.model_dir.text())
        dialog.close()

    def test_recognition_language_only_updates_a_conflicting_source(self) -> None:
        dialog = SettingsDialog(AppConfig())
        dialog.model_variant.setCurrentIndex(
            dialog.model_variant.findData("multilingual")
        )
        self.assertEqual(dialog.source_lang.currentData(), "AUTO")

        dialog.source_lang.setCurrentIndex(dialog.source_lang.findData("EN"))
        dialog.asr_language.setCurrentIndex(dialog.asr_language.findData("ja"))
        self.assertEqual(dialog.source_lang.currentData(), "JA")

        dialog.source_lang.setCurrentIndex(dialog.source_lang.findData("AUTO"))
        dialog.asr_language.setCurrentIndex(dialog.asr_language.findData("ko"))
        self.assertEqual(dialog.source_lang.currentData(), "AUTO")

        dialog.source_lang.setCurrentIndex(dialog.source_lang.findData("EN"))
        dialog.asr_language.setCurrentIndex(dialog.asr_language.findData("tr"))
        self.assertEqual(dialog.source_lang.currentData(), "AUTO")
        dialog.close()

    def test_single_language_models_expose_their_actual_language(self) -> None:
        dialog = SettingsDialog(AppConfig())
        self.assertFalse(dialog.asr_language.isEnabled())
        self.assertEqual(dialog.asr_language.currentData(), "en")

        dialog.model_variant.setCurrentIndex(
            dialog.model_variant.findData("chinese")
        )
        self.assertFalse(dialog.asr_language.isEnabled())
        self.assertEqual(dialog.asr_language.count(), 1)
        self.assertEqual(dialog.asr_language.currentData(), "zh")
        self.assertEqual(dialog.source_lang.currentData(), "ZH")
        dialog.close()

    def test_appearance_controls_round_trip_all_exposed_values(self) -> None:
        config = AppConfig()
        config.subtitle.mode = "source"
        config.subtitle.max_rows = 5
        config.subtitle.font_family = self.qt_app.font().family()
        config.subtitle.source_size = 21
        config.subtitle.translation_size = 23
        config.subtitle.font_weight = 700
        config.subtitle.text_color = "#ffeecc"
        config.subtitle.outline_color = "#112233"
        config.subtitle.outline_width = 1.5
        config.subtitle.shadow = False
        config.subtitle.align = "right"
        config.subtitle.background = "block"
        config.subtitle.background_color = "rgba(1,2,3,0.7)"
        config.subtitle.padding = 19
        config.subtitle.stay_ms = 7400
        dialog = SettingsDialog(config)

        values = dialog.values().subtitle

        for name in (
            "mode", "max_rows", "font_family", "source_size",
            "translation_size", "font_weight", "text_color", "outline_color",
            "outline_width", "shadow", "align", "background",
            "background_color", "padding", "stay_ms",
        ):
            self.assertEqual(getattr(values, name), getattr(config.subtitle, name))
        dialog.close()


class HistoryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_live_entry_keeps_complete_source_and_translation_separate(self) -> None:
        dialog = HistoryDialog()
        dialog.set_live(
            source="A complete current source sentence.",
            translation="一条完整的当前译文。",
        )
        item = dialog._find_item("live")

        self.assertIsNotNone(item)
        self.assertIn("实时", item.text())
        self.assertIn("\n\nA complete current source sentence.", item.text())
        self.assertIn("\n\n一条完整的当前译文。", item.text())
        self.assertNotIn("原文  ", item.text())
        self.assertNotIn("译文  ", item.text())
        dialog.set_live(source="A newer source revision.")
        self.assertIn("一条完整的当前译文。", item.text())
        dialog.set_live(translation="更新后的实时译文。")
        self.assertIn("更新后的实时译文。", item.text())
        dialog.close()

    def test_empty_state_and_count_follow_history_content(self) -> None:
        dialog = HistoryDialog()
        self.assertIs(dialog.content.currentWidget(), dialog.empty_page)
        self.assertEqual(dialog.count_label.text(), "0 条")
        self.assertFalse(dialog.clear_button.isEnabled())

        dialog.append(HistoryRecord("12:00:00", "Source", "译文", "deepl"))

        self.assertIs(dialog.content.currentWidget(), dialog.list)
        self.assertEqual(dialog.count_label.text(), "1 条")
        self.assertIn("DeepL", dialog.list.item(0).text())
        self.assertTrue(dialog.clear_button.isEnabled())
        dialog.close()

    def test_live_entry_is_separate_until_it_is_committed(self) -> None:
        dialog = HistoryDialog()
        dialog.set_live(source="Current source", translation="当前译文")
        self.assertEqual(dialog.records, [])

        record = HistoryRecord("12:00:00", "Current source", "", "llama")
        index = dialog.commit_live(record)

        self.assertEqual(index, 0)
        self.assertEqual(len(dialog.records), 1)
        self.assertEqual(dialog.records[0].translation, "当前译文")
        self.assertIsNone(dialog._find_item("live"))
        self.assertIsNotNone(dialog._find_item(0))
        dialog.close()

    def test_append_updates_the_list_without_a_full_refresh(self) -> None:
        dialog = HistoryDialog()
        with patch.object(dialog, "refresh") as refresh:
            index = dialog.append(
                HistoryRecord("12:00:00", "Source", "译文", "llama")
            )

        self.assertEqual(index, 0)
        refresh.assert_not_called()
        self.assertIsNotNone(dialog._find_item(0))
        dialog.close()

    def test_history_initially_renders_only_the_latest_page(self) -> None:
        dialog = HistoryDialog()
        total = HISTORY_PAGE_SIZE * 2 + 50
        for index in range(total):
            dialog.append(
                HistoryRecord("12:00:00", f"Source {index}", "", "llama")
            )

        self.assertEqual(len(dialog.records), total)
        self.assertEqual(dialog.list.count(), HISTORY_PAGE_SIZE)
        self.assertIsNone(dialog._find_item(0))
        self.assertIsNotNone(dialog._find_item(total - 1))

        dialog.follow_live = False
        dialog._load_older()
        self.qt_app.processEvents()
        self.assertEqual(dialog.list.count(), HISTORY_PAGE_SIZE * 2)
        dialog._load_older()
        self.qt_app.processEvents()
        self.assertEqual(dialog.list.count(), total)
        dialog.close()

    def test_history_cap_uses_stable_ids_for_late_translations(self) -> None:
        dialog = HistoryDialog()
        first_id = dialog._store_record(
            HistoryRecord("12:00:00", "Expired", "", "llama")
        )
        last_id = first_id
        for index in range(MAX_HISTORY_RECORDS + 4):
            last_id = dialog._store_record(
                HistoryRecord("12:00:00", f"Source {index}", "", "llama")
            )

        self.assertEqual(len(dialog.records), MAX_HISTORY_RECORDS)
        self.assertNotIn(first_id, dialog._records_by_id)
        dialog.update_translation(first_id, "不应写入其他记录")
        dialog.update_translation(last_id, "最新译文")
        self.assertEqual(dialog._records_by_id[last_id].translation, "最新译文")
        self.assertNotIn(
            "不应写入其他记录",
            [record.translation for record in dialog.records],
        )
        dialog.close()

    def test_clearing_history_keeps_the_live_mirror(self) -> None:
        dialog = HistoryDialog()
        dialog.append(HistoryRecord("12:00:00", "Old", "旧", "llama"))
        dialog.set_live(source="Current", translation="当前")

        dialog.clear()

        self.assertEqual(dialog.records, [])
        self.assertIsNotNone(dialog._find_item("live"))
        dialog.close()

    def test_live_item_uses_a_subdued_dark_palette_color(self) -> None:
        dialog = HistoryDialog()
        palette = dialog.list.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#f1f3f4"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#2f6fed"))
        dialog.list.setPalette(palette)
        dialog._apply_palette()
        dialog.set_live(source="Current")
        live = dialog._find_item("live")

        self.assertLess(live.background().color().lightness(), 100)
        self.assertEqual(live.foreground().color(), QColor("#f1f3f4"))
        dialog.close()

    def test_live_updates_do_not_pull_a_manual_reader_to_the_bottom(self) -> None:
        dialog = HistoryDialog()
        dialog.resize(520, 280)
        for index in range(20):
            dialog.append(
                HistoryRecord(
                    f"12:00:{index:02d}",
                    f"Source line {index} " * 4,
                    f"译文 {index} " * 4,
                    "llama",
                )
            )
        dialog.set_live(source="Current source", translation="当前译文")
        dialog.show()
        self.qt_app.processEvents()
        scrollbar = dialog.list.verticalScrollBar()
        scrollbar.setValue(maximum := scrollbar.maximum() // 3)
        self.qt_app.processEvents()
        self.assertFalse(dialog.follow_live)

        for index in range(5):
            dialog.set_live(
                source=f"Current source revision {index} " * 3,
                translation=f"实时译文 {index}",
            )
            self.qt_app.processEvents()

        self.assertEqual(scrollbar.value(), maximum)
        dialog.close()


class ConfigTests(unittest.TestCase):
    def test_utf8_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig()
            config.translation.glossary = {"Vault": "避难所"}
            save_config(config, path)
            loaded, _ = load_config(path)
            self.assertEqual(loaded.translation.glossary["Vault"], "避难所")

    def test_deepl_key_is_encrypted_at_rest_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig()
            config.translation.deepl_api_key = "local-test-key"

            save_config(config, path)

            stored = path.read_text(encoding="utf-8")
            self.assertNotIn("local-test-key", stored)
            self.assertIn("dpapi:", stored)
            loaded, _ = load_config(path)
            self.assertEqual(loaded.translation.deepl_api_key, "local-test-key")

    def test_google2_key_round_trips_as_editable_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig()
            config.translation.google2_api_key = "replacement-google2-key"

            save_config(config, path)

            loaded, _ = load_config(path)
            self.assertEqual(
                loaded.translation.google2_api_key,
                "replacement-google2-key",
            )

    def test_invalid_json_is_backed_up_and_defaults_are_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{invalid", encoding="utf-8")

            loaded, _ = load_config(path)

            self.assertEqual(loaded, AppConfig())
            self.assertTrue(path.with_name("config.invalid.json").is_file())
            self.assertTrue(getattr(loaded, "_load_warning", ""))

    def test_invalid_types_and_ranges_fall_back_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                '{"translation":{"backend":42,"timeout_ms":999999},'
                '"subtitle":{"mode":"unknown","max_rows":500}}',
                encoding="utf-8",
            )

            loaded, _ = load_config(path)

            self.assertEqual(loaded.translation.backend, "llama")
            self.assertEqual(loaded.translation.timeout_ms, 120000)
            self.assertEqual(loaded.subtitle.mode, "bilingual")
            self.assertEqual(loaded.subtitle.max_rows, 6)

    def test_new_features_keep_existing_defaults(self) -> None:
        config = AppConfig()
        self.assertEqual(config.asr.model_variant, "english")
        self.assertEqual(config.asr.language, "en")
        self.assertEqual(config.asr.auto_standby_seconds, 0)
        self.assertEqual(config.translation.backend, "llama")
        self.assertEqual(config.translation.source_lang, "EN")
        self.assertEqual(config.translation.target_lang, "ZH-HANS")
        name, _ = model_download_spec(config)
        self.assertNotEqual(name, MULTILINGUAL_MODEL_NAME)

    def test_example_config_contains_all_new_options(self) -> None:
        loaded, _ = load_config(Path(__file__).resolve().parent.parent / "config.example.json")
        self.assertEqual(loaded.asr.model_variant, "english")
        self.assertEqual(loaded.asr.language, "en")
        self.assertEqual(loaded.asr.auto_standby_seconds, 0)
        self.assertEqual(loaded.translation.deepl_api_plan, "free")
        self.assertEqual(loaded.translation.source_lang, "EN")
        self.assertEqual(loaded.translation.target_lang, "ZH-HANS")

    def test_legacy_deepl_target_language_migrates_to_shared_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                '{"translation":{"deepl_target_lang":"JA"}}',
                encoding="utf-8",
            )

            loaded, _ = load_config(path)

        self.assertEqual(loaded.translation.source_lang, "EN")
        self.assertEqual(loaded.translation.target_lang, "JA")

    def test_model_catalog_declares_language_compatibility(self) -> None:
        self.assertEqual(MODEL_CATALOG["english"].supported_languages, ("en",))
        self.assertEqual(MODEL_CATALOG["chinese"].supported_languages, ("zh",))
        self.assertTrue(MODEL_CATALOG["multilingual"].supports_auto_language)
        self.assertEqual(
            MODEL_CATALOG["multilingual"].supported_languages,
            NEMOTRON_MULTILINGUAL_LANGUAGES,
        )

    def test_model_language_is_normalized_to_its_compatibility_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                '{"asr":{"model_variant":"chinese","language":"ja"}}',
                encoding="utf-8",
            )

            loaded, _ = load_config(path)

        self.assertEqual(loaded.asr.language, "zh")

    def test_model_completeness_requires_all_four_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = AppConfig()
            config.asr.model_dir = directory
            for name in ("encoder", "decoder", "joiner"):
                (Path(directory) / getattr(config.asr, name)).write_bytes(b"x")
            self.assertFalse(model_is_complete(config))
            (Path(directory) / config.asr.tokens).write_text("token", encoding="utf-8")
            self.assertTrue(model_is_complete(config))

    def test_model_download_integrity_is_pinned_for_each_preset(self) -> None:
        config = AppConfig()
        english = model_download_integrity(config)
        config.asr.model_variant = "multilingual"
        multilingual = model_download_integrity(config)

        self.assertGreater(english[0], 0)
        self.assertEqual(len(english[1]), 64)
        self.assertGreater(multilingual[0], 0)
        self.assertEqual(len(multilingual[1]), 64)
        self.assertNotEqual(english, multilingual)

    def test_chinese_model_preset_updates_its_compatible_files(self) -> None:
        config = AppConfig()

        apply_model_preset(config.asr, "chinese")

        self.assertEqual(config.asr.model_variant, "chinese")
        self.assertIn(CHINESE_MODEL_NAME, config.asr.model_dir)
        self.assertEqual(config.asr.encoder, "encoder.int8.onnx")
        self.assertEqual(config.asr.decoder, "decoder.onnx")
        self.assertEqual(config.asr.joiner, "joiner.int8.onnx")


class ModelDownloadTests(unittest.TestCase):
    @staticmethod
    def _archive() -> bytes:
        data = io.BytesIO()
        root = (
            "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-"
            "2026-04-25"
        )
        with tarfile.open(fileobj=data, mode="w:bz2") as bundle:
            for name in (
                "encoder.int8.onnx",
                "decoder.int8.onnx",
                "joiner.int8.onnx",
                "tokens.txt",
            ):
                content = name.encode()
                info = tarfile.TarInfo(f"{root}/{name}")
                info.size = len(content)
                bundle.addfile(info, io.BytesIO(content))
        return data.getvalue()

    def test_download_extracts_a_complete_model_and_reports_progress(self) -> None:
        payload = self._archive()

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "model"
            destination.mkdir()
            (destination / "obsolete.onnx").write_bytes(b"old")
            completed: list[bool] = []
            progress: list[tuple[int, int]] = []
            worker = ModelDownloadWorker(
                destination,
                expected_size=len(payload),
                expected_sha256=hashlib.sha256(payload).hexdigest(),
            )
            worker.completed.connect(lambda: completed.append(True))
            worker.progress.connect(
                lambda downloaded, total: progress.append((downloaded, total))
            )
            with patch(
                "captions.model_download.urllib.request.urlopen",
                return_value=Response(payload),
            ):
                worker.run()

            self.assertEqual(completed, [True])
            self.assertTrue(progress)
            self.assertTrue((destination / "encoder.int8.onnx").is_file())
            self.assertFalse((destination / "obsolete.onnx").exists())
            self.assertFalse(any(Path(directory).glob(".*.download")))

    def test_download_rejects_a_failed_integrity_check(self) -> None:
        payload = self._archive()

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "model"
            errors: list[str] = []
            worker = ModelDownloadWorker(
                destination,
                expected_size=len(payload),
                expected_sha256="0" * 64,
            )
            worker.error.connect(errors.append)
            with patch(
                "captions.model_download.urllib.request.urlopen",
                return_value=Response(payload),
            ):
                worker.run()

            self.assertTrue(errors)
            self.assertFalse(destination.exists())
            self.assertFalse(any(Path(directory).glob(".*.download")))


if __name__ == "__main__":
    unittest.main()
