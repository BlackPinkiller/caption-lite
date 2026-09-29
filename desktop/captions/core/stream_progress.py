"""Coalesce intermediate text without delaying its first or final delivery."""
from __future__ import annotations

import time
from typing import Callable


class StreamProgress:
    def __init__(self, emit: Callable[[str], None], interval: float = 0.04) -> None:
        self.emit = emit
        self.interval = interval
        self.last_sent_at: float | None = None
        self.last_text = ""
        self.pending = ""

    def update(self, text: str, *, now: float | None = None) -> None:
        self.pending = text
        now = time.monotonic() if now is None else now
        if self.last_sent_at is None or now - self.last_sent_at >= self.interval:
            self.flush(now=now)

    def flush(self, *, now: float | None = None) -> None:
        if self.pending and self.pending != self.last_text:
            self.last_text = self.pending
            self.last_sent_at = time.monotonic() if now is None else now
            self.emit(self.pending)
