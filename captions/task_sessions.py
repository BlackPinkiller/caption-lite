from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from captions.audio_asr import AudioAsrWorker
from captions.config import AppConfig
from captions.model_download import ModelDownloadWorker


class CaptureSession(QObject):
    partial = Signal(str, int)
    endpoint = Signal()
    status = Signal(str)
    model_ready = Signal()
    auto_standby_changed = Signal(bool)
    error = Signal(str)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: AudioAsrWorker | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None

    def start(self, config: AppConfig) -> bool:
        if self.running:
            return False
        thread = QThread(self)
        worker = AudioAsrWorker(config)
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

    def _thread_finished(self) -> None:
        if self.sender() is not self.thread:
            return
        self.thread = None
        self.worker = None
        self.finished.emit()


class ModelDownloadSession(QObject):
    progress = Signal(int, int)
    status = Signal(str)
    completed = Signal()
    cancelled = Signal()
    error = Signal(str)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: ModelDownloadWorker | None = None

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
    ) -> bool:
        if self.running:
            return False
        thread = QThread(self)
        worker = ModelDownloadWorker(
            destination,
            model_name=model_name,
            model_url=model_url,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )
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
        if self.sender() is not self.thread:
            return
        self.thread = None
        self.worker = None
        self.finished.emit()
