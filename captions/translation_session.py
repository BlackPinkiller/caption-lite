from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from captions.config import SegmentationConfig, TranslationConfig
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

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.translator = Translator()
        self._key_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="google2-key",
        )
        self._key_future: Future | None = None
        self.jobs: dict[int, TranslationJob] = {}
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
        self._reset_preview_schedule()
        self._discard_preview_jobs()
        self.translator.cancel_pending()
        generation = self.translator.translate(source, history, config)
        self.jobs[generation] = TranslationJob(
            "commit", record_id, source, cue_id
        )
        return generation

    def request_test(self, text: str, config: TranslationConfig) -> int:
        generation = self.translator.translate(text, [], config)
        self.jobs[generation] = TranslationJob("test", None, text, 0)
        return generation

    def schedule_preview(
        self,
        source: str,
        history: list[HistoryRecord],
        config: TranslationConfig,
        segmentation: SegmentationConfig,
        cue_id: int,
    ) -> None:
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

    def request_google2_key(self) -> None:
        if self._key_future is not None and not self._key_future.done():
            return
        future = self._key_executor.submit(Translator.acquire_google2_api_key)
        self._key_future = future

        def done(completed: Future) -> None:
            try:
                key = completed.result()
            except Exception as error:
                self.google2_key_error.emit(str(error))
            else:
                self.google2_key_ready.emit(key)

        future.add_done_callback(done)

    def close(self) -> None:
        self.preview_timer.stop()
        self._key_executor.shutdown(wait=False, cancel_futures=True)
        self.translator.close()

    @Slot()
    def _send_pending_preview(self) -> None:
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
        generation = self.translator.translate(
            source, self.pending_history, config, preview=True
        )
        self.jobs[generation] = TranslationJob(
            "preview", None, source, self.pending_cue_id
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
        self.jobs = {
            generation: job
            for generation, job in self.jobs.items()
            if job.kind != "preview"
        }
        self.previews_discarded.emit()

    @Slot(int)
    def _started(self, generation: int) -> None:
        job = self.jobs.get(generation)
        if job is not None:
            self.started.emit(generation, job)

    @Slot(int, str)
    def _progress(self, generation: int, text: str) -> None:
        job = self.jobs.get(generation)
        if job is not None:
            self.progress.emit(generation, job, text)

    @Slot(int, str)
    def _result(self, generation: int, text: str) -> None:
        job = self.jobs.pop(generation, None)
        if job is not None:
            self.result.emit(generation, job, text)

    @Slot(int, str)
    def _error(self, generation: int, message: str) -> None:
        job = self.jobs.pop(generation, None)
        if job is not None:
            self.error.emit(generation, job, message)

    @Slot(int)
    def _cancelled(self, generation: int) -> None:
        job = self.jobs.pop(generation, None)
        if job is not None:
            self.cancelled.emit(generation, job)
