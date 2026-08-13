from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import threading
import time

import httpx

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from captions.config import SegmentationConfig, TranslationConfig
from captions.core.diagnostics import Diagnostics, NULL_DIAGNOSTICS
from captions.translation import HistoryRecord, Translator


@dataclass(frozen=True)
class TranslationJob:
    kind: str
    index: int | None
    source: str
    cue_id: int


class TranslationSession(QObject):
    started = Signal(int, object)
    progress = Signal(int, object, str)
    result = Signal(int, object, str)
    error = Signal(int, object, str)
    cancelled = Signal(int, object)
    previews_discarded = Signal()
    google2_key_ready = Signal(str)
    google2_key_error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        diagnostics: Diagnostics = NULL_DIAGNOSTICS,
    ) -> None:
        super().__init__(parent)
        self.diagnostics = diagnostics
        self.translator = Translator()
        self._key_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="google2-key",
        )
        self._key_future: Future | None = None
        self._key_client = httpx.Client(http2=False)
        self._closing = False
        self._shutdown_complete = threading.Event()
        self._shutdown_thread: threading.Thread | None = None
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(20)
        self._shutdown_timer.timeout.connect(self._poll_shutdown)
        self.jobs: dict[int, TranslationJob] = {}
        self._progress_logged: set[int] = set()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._send_pending_preview)
        self.pending_preview_text = ""
        self.pending_history: list[HistoryRecord] = []
        self.pending_config: TranslationConfig | None = None
        self.pending_segmentation: SegmentationConfig | None = None
        self.pending_cue_id = 0
        self.last_preview_text = ""
        self.last_preview_sent_at = 0.0
        self.translator.signals.started.connect(self._started)
        self.translator.signals.progress.connect(self._progress)
        self.translator.signals.result.connect(self._result)
        self.translator.signals.error.connect(self._error)
        self.translator.signals.cancelled.connect(self._cancelled)

    def request_commit(
        self,
        source: str,
        history: list[HistoryRecord],
        config: TranslationConfig,
        *,
        record_id: int,
        cue_id: int,
    ) -> int:
        if self._closing:
            return 0
        self._reset_preview_schedule()
        self._discard_preview_jobs()
        self.translator.cancel_pending()
        job = TranslationJob("commit", record_id, source, cue_id)
        generation = self.translator.translate(
            source,
            history,
            config,
            on_registered=lambda value: self._register_job(
                value,
                job,
                backend=config.backend,
            ),
        )
        if generation not in self.jobs:
            self._register_job(generation, job, backend=config.backend)
        return generation

    def request_test(self, text: str, config: TranslationConfig) -> int:
        if self._closing:
            return 0
        job = TranslationJob("test", None, text, 0)
        generation = self.translator.translate(
            text,
            [],
            config,
            on_registered=lambda value: self._register_job(
                value,
                job,
                backend=config.backend,
            ),
        )
        if generation not in self.jobs:
            self._register_job(generation, job, backend=config.backend)
        return generation

    def schedule_preview(
        self,
        source: str,
        history: list[HistoryRecord],
        config: TranslationConfig,
        segmentation: SegmentationConfig,
        cue_id: int,
    ) -> None:
        if self._closing:
            return
        source = source.strip()
        self.pending_preview_text = source
        self.pending_history = history
        self.pending_config = config
        self.pending_segmentation = segmentation
        self.pending_cue_id = cue_id
        if len(source) < segmentation.preview_min_chars:
            return
        if not self.last_preview_text:
            self._send_pending_preview()
            return
        common = 0
        for old, new in zip(self.last_preview_text, source):
            if old != new:
                break
            common += 1
        changed = max(len(self.last_preview_text), len(source)) - common
        if changed >= segmentation.preview_char_delta:
            self._send_pending_preview()
            return
        elapsed_ms = (time.monotonic() - self.last_preview_sent_at) * 1000
        remaining = max(0, segmentation.preview_interval_ms - int(elapsed_ms))
        self.preview_timer.start(remaining)

    def has_job(self, generation: int) -> bool:
        return generation in self.jobs

    def cancel_all(self) -> None:
        self._reset_preview_schedule()
        self.jobs.clear()
        self._progress_logged.clear()
        self.translator.cancel_all()
        self.previews_discarded.emit()
        self.diagnostics.event("translation.disabled")

    def request_google2_key(self) -> None:
        if self._closing:
            return
        if self._key_future is not None and not self._key_future.done():
            return
        future = self._key_executor.submit(
            Translator.acquire_google2_api_key,
            client=self._key_client,
        )
        self._key_future = future

        def done(completed: Future) -> None:
            if self._closing:
                return
            try:
                key = completed.result()
            except Exception as error:
                self.google2_key_error.emit(str(error))
            else:
                self.google2_key_ready.emit(key)

        future.add_done_callback(done)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._reset_preview_schedule()
        self.jobs.clear()
        self._progress_logged.clear()
        if self._key_future is not None:
            self._key_future.cancel()
        try:
            self._key_client.close()
        except Exception:
            pass
        self._key_executor.shutdown(wait=False, cancel_futures=True)
        self.translator.close()
        self._shutdown_thread = threading.Thread(
            target=self._finish_shutdown,
            name="translation-shutdown",
            daemon=True,
        )
        self._shutdown_thread.start()
        self._shutdown_timer.start()

    @property
    def shutting_down(self) -> bool:
        return self._closing and not self._shutdown_complete.is_set()

    def _finish_shutdown(self) -> None:
        try:
            self._key_executor.shutdown(wait=True, cancel_futures=True)
            self.translator.wait_closed()
        finally:
            self._shutdown_complete.set()

    @Slot()
    def _poll_shutdown(self) -> None:
        if not self._shutdown_complete.is_set():
            return
        self._shutdown_timer.stop()
        if self._shutdown_thread is not None:
            self._shutdown_thread.join()
            self._shutdown_thread = None
        self._key_future = None
        self.finished.emit()

    @Slot()
    def _send_pending_preview(self) -> None:
        if self._closing:
            return
        source = self.pending_preview_text.strip()
        config = self.pending_config
        segmentation = self.pending_segmentation
        if (
            config is None
            or segmentation is None
            or len(source) < segmentation.preview_min_chars
        ):
            return
        if source == self.last_preview_text:
            return
        self.preview_timer.stop()
        self.last_preview_text = source
        self.last_preview_sent_at = time.monotonic()
        job = TranslationJob("preview", None, source, self.pending_cue_id)
        generation = self.translator.translate(
            source,
            self.pending_history,
            config,
            preview=True,
            on_registered=lambda value: self._register_job(
                value,
                job,
                backend=config.backend,
            ),
        )
        if generation not in self.jobs:
            self._register_job(generation, job, backend=config.backend)

    def _register_job(
        self,
        generation: int,
        job: TranslationJob,
        *,
        backend: str,
    ) -> None:
        self.jobs[generation] = job
        self.diagnostics.event(
            "translation.submitted",
            generation=generation,
            kind=job.kind,
            cue_id=job.cue_id,
            record_id=job.index,
            backend=backend,
            source=job.source,
        )

    def _reset_preview_schedule(self) -> None:
        self.preview_timer.stop()
        self.pending_preview_text = ""
        self.pending_history = []
        self.pending_config = None
        self.pending_segmentation = None
        self.pending_cue_id = 0
        self.last_preview_text = ""
        self.last_preview_sent_at = 0.0

    def _discard_preview_jobs(self) -> None:
        preview_generations = {
            generation
            for generation, job in self.jobs.items()
            if job.kind == "preview"
        }
        self.jobs = {
            generation: job
            for generation, job in self.jobs.items()
            if job.kind != "preview"
        }
        self._progress_logged.difference_update(preview_generations)
        self.previews_discarded.emit()

    @Slot(int)
    def _started(self, generation: int) -> None:
        job = self.jobs.get(generation)
        if job is not None:
            self.diagnostics.event(
                "translation.started",
                generation=generation,
                kind=job.kind,
                cue_id=job.cue_id,
                record_id=job.index,
            )
            self.started.emit(generation, job)

    @Slot(int, str)
    def _progress(self, generation: int, text: str) -> None:
        job = self.jobs.get(generation)
        if job is not None:
            if generation not in self._progress_logged:
                self._progress_logged.add(generation)
                self.diagnostics.event(
                    "translation.first_progress",
                    generation=generation,
                    kind=job.kind,
                    cue_id=job.cue_id,
                    record_id=job.index,
                    translation=text,
                )
            self.progress.emit(generation, job, text)

    @Slot(int, str)
    def _result(self, generation: int, text: str) -> None:
        job = self.jobs.pop(generation, None)
        self._progress_logged.discard(generation)
        if job is not None:
            self.diagnostics.event(
                "translation.completed",
                generation=generation,
                kind=job.kind,
                cue_id=job.cue_id,
                record_id=job.index,
                translation=text,
            )
            self.result.emit(generation, job, text)

    @Slot(int, str)
    def _error(self, generation: int, message: str) -> None:
        job = self.jobs.pop(generation, None)
        self._progress_logged.discard(generation)
        if job is not None:
            self.diagnostics.event(
                "translation.failed",
                generation=generation,
                kind=job.kind,
                cue_id=job.cue_id,
                record_id=job.index,
                error=message,
            )
            self.error.emit(generation, job, message)

    @Slot(int)
    def _cancelled(self, generation: int) -> None:
        job = self.jobs.pop(generation, None)
        self._progress_logged.discard(generation)
        if job is not None:
            self.diagnostics.event(
                "translation.cancelled",
                generation=generation,
                kind=job.kind,
                cue_id=job.cue_id,
                record_id=job.index,
            )
            self.cancelled.emit(generation, job)
