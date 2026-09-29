from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal

from captions.application.audio_asr import AudioAsrWorker
from captions.core.settings import AppConfig
from captions.core.diagnostics import Diagnostics, NULL_DIAGNOSTICS


class CaptureSession(QObject):
    partial = Signal(str, int)
    endpoint = Signal()
    paused = Signal(int)
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
        queued = Qt.ConnectionType.QueuedConnection
        worker.partial.connect(self.partial, queued)
        worker.endpoint.connect(self.endpoint, queued)
        worker.paused.connect(self.paused, queued)
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

    def pause(self) -> int:
        if self.worker is not None:
            return self.worker.pause()
        return 0

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
