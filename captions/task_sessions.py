from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from captions.audio_asr import AudioAsrWorker
from captions.config import AppConfig
from captions.core.diagnostics import Diagnostics, NULL_DIAGNOSTICS
from captions.high_precision_runtime import HighPrecisionInstallWorker
from captions.model_download import ModelDownloadWorker


class CaptureSession(QObject):
    partial = Signal(str, int)
    endpoint = Signal()
    status = Signal(str)
    model_ready = Signal()
    auto_standby_changed = Signal(bool)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        diagnostics: Diagnostics = NULL_DIAGNOSTICS,
    ) -> None:
        super().__init__(parent)
        self.diagnostics = diagnostics
        self.thread: QThread | None = None
        self.worker: AudioAsrWorker | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None

    def start(self, config: AppConfig) -> bool:
        if self.running:
            return False
        thread = QThread(self)
        worker = AudioAsrWorker(config, diagnostics=self.diagnostics)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.partial.connect(self.partial.emit)
        worker.endpoint.connect(self.endpoint.emit)
        worker.status.connect(self.status.emit)
        worker.model_ready.connect(self.model_ready.emit)
        worker.auto_standby_changed.connect(self.auto_standby_changed.emit)
        worker.error.connect(self.error.emit)
        worker.stopped.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self.thread = thread
        self.worker = worker
        thread.start()
        return True

    def pause(self) -> None:
        if self.worker is not None:
            self.worker.pause()

    def resume(self) -> None:
        if self.worker is not None:
            self.worker.resume()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()

    def set_auto_standby_seconds(self, seconds: int) -> None:
        if self.worker is not None:
            self.worker.set_auto_standby_seconds(seconds)

    def set_silence_min_chars(self, chars: int) -> None:
        if self.worker is not None:
            self.worker.set_silence_min_chars(chars)

    def _thread_finished(self) -> None:
        thread = self.thread
        if self.sender() is not thread:
            return
        # QThread.finished is emitted before the native thread has necessarily
        # completed its thread_local cleanup. Do not let QApplication teardown
        # destroy Qt TLS while that final cleanup is still running.
        thread.wait()
        self.thread = None
        self.worker = None
        self.finished.emit()


class ModelDownloadSession(QObject):
    progress = Signal(object, object)
    status = Signal(str)
    completed = Signal()
    cancelled = Signal()
    error = Signal(str)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: ModelDownloadWorker | HighPrecisionInstallWorker | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None

    def start(
        self,
        destination: Path,
        *,
        model_name: str,
        model_url: str,
        expected_size: int,
        expected_sha256: str,
        required_files: tuple[str, ...],
    ) -> bool:
        if self.running:
            return False
        worker = ModelDownloadWorker(
            destination,
            model_name=model_name,
            model_url=model_url,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            required_files=required_files,
        )
        return self._start_worker(worker)

    def start_high_precision(self, destination: Path) -> bool:
        if self.running:
            return False
        return self._start_worker(HighPrecisionInstallWorker(destination))

    def _start_worker(
        self,
        worker: ModelDownloadWorker | HighPrecisionInstallWorker,
    ) -> bool:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress.emit)
        worker.status.connect(self.status.emit)
        worker.completed.connect(self.completed.emit)
        worker.cancelled.connect(self.cancelled.emit)
        worker.error.connect(self.error.emit)
        worker.stopped.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self.thread = thread
        self.worker = worker
        thread.start()
        return True

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    def _thread_finished(self) -> None:
        thread = self.thread
        if self.sender() is not thread:
            return
        thread.wait()
        self.thread = None
        self.worker = None
        self.finished.emit()
