"""Flush coalesced progress even while a synchronous provider stops yielding."""
from __future__ import annotations

import threading
import time
from typing import Callable

from captions.core.stream_progress import StreamProgress


class TimedStreamProgress:
    def __init__(self, emit: Callable[[str], None], interval: float = 0.04) -> None:
        self._progress = StreamProgress(emit, interval)
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._closed = False

    def update(self, text: str) -> None:
        with self._lock:
            if self._closed:
                return
            now = time.monotonic()
            self._progress.update(text, now=now)
            if self._progress.pending == self._progress.last_text:
                self._cancel_timer()
            elif self._timer is None:
                delay = max(0.0, self._progress.interval - (now - self._progress.last_sent_at))
                timer = threading.Timer(delay, lambda: self._flush_pending(timer))
                timer.name = "translation-progress"
                timer.daemon = True
                self._timer = timer
                timer.start()

    def _flush_pending(self, timer: threading.Timer) -> None:
        with self._lock:
            if self._closed or self._timer is not timer:
                return
            self._timer = None
            self._progress.flush()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def close(self) -> None:
        # Serialize flush and close so progress cannot arrive after result/error.
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel_timer()
            self._progress.flush()
