from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from captions.adapters.recognition_router import RecognitionRouter
from captions.adapters.sherpa_onnx_recognition import SherpaStreamingRecognition
from captions.adapters.transformers_recognition import _activate_external_runtime
from captions.config import AppConfig, load_config, model_is_complete
from captions.high_precision_runtime import (
    RUNTIME_REVISION,
    RuntimeFile,
    _repair_moved_venv,
    high_precision_runtime_ready,
)
from captions.task_sessions import ModelDownloadSession
from captions.ui.settings_dialog import SettingsDialog


class HighPrecisionConfigTests(unittest.TestCase):
    def test_fp32_is_kept_only_for_compatible_nemotron_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                '{"asr":{"model_variant":"english_1120","precision":"fp32"}}',
                encoding="utf-8",
            )
            compatible, _ = load_config(path)
            path.write_text(
                '{"asr":{"model_variant":"chinese","precision":"fp32"}}',
                encoding="utf-8",
            )
            incompatible, _ = load_config(path)

        self.assertEqual(compatible.asr.precision, "fp32")
        self.assertEqual(incompatible.asr.precision, "int8")

    def test_fp32_completeness_uses_the_independent_runtime(self) -> None:
        config = AppConfig()
        config.asr.precision = "fp32"
        with patch(
            "captions.high_precision_runtime.high_precision_runtime_ready",
            return_value=True,
        ) as ready:
            self.assertTrue(model_is_complete(config))
        ready.assert_called_once()


class HighPrecisionRuntimeTests(unittest.TestCase):
    def test_moved_runtime_rewrites_venv_launchers_to_final_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            base = runtime / "python" / "cpython-3.12.0-windows-x86_64-none"
            scripts = runtime / ".venv" / "Scripts"
            base.mkdir(parents=True)
            scripts.mkdir(parents=True)
            (base / "python.exe").write_bytes(b"base-python")
            (base / "pythonw.exe").write_bytes(b"base-pythonw")
            (scripts / "python.exe").write_bytes(b"staging-launcher")
            (scripts / "pythonw.exe").write_bytes(b"staging-launcher")
            config = runtime / ".venv" / "pyvenv.cfg"
            config.write_text("home = old-staging-path\ninclude-system-site-packages = false\n")

            with patch(
                "captions.high_precision_runtime.subprocess.run",
                return_value=SimpleNamespace(returncode=0),
            ) as run:
                _repair_moved_venv(runtime)

            self.assertEqual((scripts / "python.exe").read_bytes(), b"base-python")
            self.assertTrue(config.read_text().startswith(f"home = {base}\n"))
            run.assert_called_once()

    def test_external_runtime_adds_its_standard_library_and_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            site_packages = runtime / ".venv" / "Lib" / "site-packages"
            base = runtime / "python" / "cpython-3.12.0-windows-x86_64-none"
            site_packages.mkdir(parents=True)
            (base / "Lib").mkdir(parents=True)
            (base / "DLLs").mkdir()
            original = sys.path.copy()
            try:
                _activate_external_runtime(site_packages)
                self.assertEqual(
                    sys.path[:3],
                    [str(site_packages), str(base / "Lib"), str(base / "DLLs")],
                )
            finally:
                sys.path[:] = original

    def test_ready_marker_and_model_files_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app_paths = SimpleNamespace(application_dir=lambda: root)
            runtime = root / "runtime" / "nemotron-fp32"
            (runtime / ".venv" / "Scripts").mkdir(parents=True)
            (runtime / ".venv" / "Scripts" / "python.exe").write_bytes(b"x")
            (runtime / "model").mkdir()
            (runtime / "model" / "model.bin").write_bytes(b"model")
            (runtime / ".ready").write_text(
                json.dumps({"revision": RUNTIME_REVISION}),
                encoding="utf-8",
            )
            files = (RuntimeFile("model.bin", 5, "unused"),)
            with patch("captions.high_precision_runtime.MODEL_FILES", files):
                self.assertTrue(
                    high_precision_runtime_ready(app_paths=app_paths)
                )
                (runtime / "model" / "model.bin").unlink()
                self.assertFalse(
                    high_precision_runtime_ready(app_paths=app_paths)
                )

    def test_download_progress_preserves_values_above_two_gibibytes(self) -> None:
        session = ModelDownloadSession()
        observed: list[tuple[int, int]] = []
        session.progress.connect(
            lambda downloaded, total: observed.append((downloaded, total))
        )
        downloaded = 3 * 1024**3
        total = 4 * 1024**3

        session.progress.emit(downloaded, total)

        self.assertEqual(observed, [(downloaded, total)])


class RecognitionRouterTests(unittest.TestCase):
    def test_precision_selects_only_the_streaming_backend(self) -> None:
        router = RecognitionRouter()
        sherpa_stream = object()
        fp32_stream = object()
        vad = object()
        router.sherpa = SimpleNamespace(
            create_streaming=lambda config: sherpa_stream,
            create_vad=lambda config: vad,
        )
        router.transformers = SimpleNamespace(
            create_streaming=lambda config: fp32_stream,
        )
        config = AppConfig()

        self.assertIs(router.create_streaming(config), sherpa_stream)
        config.asr.precision = "fp32"
        self.assertIs(router.create_streaming(config), fp32_stream)
        self.assertIs(router.create_vad(config), vad)

    def test_sherpa_finalize_preserves_the_existing_600_ms_flush(self) -> None:
        accepted: list[np.ndarray] = []
        stream = SimpleNamespace(
            accept_waveform=lambda rate, samples: accepted.append(samples.copy())
        )
        recognizer = SimpleNamespace(
            is_ready=lambda current: False,
            get_result=lambda current: "tail",
            is_endpoint=lambda current: False,
        )
        update = SherpaStreamingRecognition(recognizer, stream).finalize()

        self.assertEqual(update.text, "tail")
        self.assertEqual(accepted[0].size, 9600)


class HighPrecisionSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_precision_control_is_conditional_and_defaults_to_lightweight(self) -> None:
        dialog = SettingsDialog(AppConfig())
        try:
            self.assertTrue(dialog.asr_precision.isVisibleTo(dialog))
            self.assertEqual(dialog.asr_precision.currentData(), "int8")
            dialog._select(dialog.asr_precision, "fp32")
            self.assertEqual(dialog.values().asr.precision, "fp32")
            dialog.set_model_status("未安装", downloadable=True)
            self.assertEqual(dialog.model_status.text(), "下载高精度识别组件…")
            dialog.set_model_status("加载失败", downloadable=True)
            self.assertEqual(dialog.model_status.text(), "重新下载高精度识别组件…")
            self.assertEqual(dialog.model_status.toolTip(), "模型：加载失败")

            dialog._select(dialog.model_variant, "chinese")
            self.assertFalse(dialog.asr_precision.isVisibleTo(dialog))
            self.assertEqual(dialog.values().asr.precision, "int8")
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
