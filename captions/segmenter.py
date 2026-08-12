from __future__ import annotations

import re
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentUpdate:
    active: str
    committed: str = ""
    forced: bool = False


class Segmenter:
    """Separates semantic commits from the recognizer's cumulative text."""

    def __init__(
        self,
        max_chars: int = 160,
        max_seconds: float = 20.0,
        split_lookback_chars: int = 32,
        split_lookahead_chars: int = 160,
    ) -> None:
        self.max_chars = max_chars
        self.max_seconds = max_seconds
        self.split_lookback_chars = split_lookback_chars
        self.split_lookahead_chars = split_lookahead_chars
        self.reset()

    def reset(self) -> None:
        self._raw = ""
        self._consumed = 0
        self._punctuated = ""
        self._started = 0.0

    @property
    def active(self) -> str:
        return self._raw[self._active_start() :]

    def _active_start(self) -> int:
        start = self._consumed
        while start < len(self._raw) and self._raw[start].isspace():
            start += 1
        return start

    def update(self, raw: str, now: float | None = None) -> SegmentUpdate:
        now = time.monotonic() if now is None else now
        raw = " ".join(raw.split())
        if not raw:
            self._raw = ""
            return SegmentUpdate("")
        if self._started == 0:
            self._started = now
        if self._consumed and not raw.startswith(self._raw[: self._consumed]):
            self.reset()
            self._started = now
        self._raw = raw
        active = self.active

        if self._punctuated and active.startswith(self._punctuated):
            committed = self._punctuated
            self._consumed = self._active_start() + len(committed)
            self._punctuated = ""
            self._started = now
            return SegmentUpdate(self.active, committed)

        if active.endswith((".", "?", "!")):
            self._punctuated = active
        else:
            self._punctuated = ""

        if self.max_seconds > 0 and now - self._started >= self.max_seconds:
            committed = active.strip()
            self._consumed = self._active_start() + len(active)
            self._punctuated = ""
            self._started = now
            return SegmentUpdate(self.active, committed, True)

        if len(active) > self.max_chars:
            decision = self._window_split(active)
            if decision is None:
                return SegmentUpdate(active)
            split, forced = decision
            committed = active[:split].strip()
            self._consumed = self._active_start() + split
            self._punctuated = ""
            self._started = now
            return SegmentUpdate(self.active, committed, forced)
        return SegmentUpdate(active)

    def flush(self, forced: bool = False) -> SegmentUpdate:
        active = self.active
        self.reset()
        return SegmentUpdate("", active, forced) if active else SegmentUpdate("")

    def _window_split(self, text: str) -> tuple[int, bool] | None:
        soft = max(1, self.max_chars)
        lookback = max(0, self.split_lookback_chars)
        lookahead = max(0, self.split_lookahead_chars)
        hard = soft + lookahead
        start = max(0, soft - lookback)
        end = min(len(text), hard)
        window = text[start:end]
        punctuation = list(re.finditer(r"[.?!](?=\s|$)", window))
        if punctuation:
            after_soft = [
                match for match in punctuation if start + match.end() >= soft
            ]
            selected = after_soft[0] if after_soft else punctuation[-1]
            return start + selected.end(), False
        if len(text) < hard:
            return None
        floor = max(0, hard - lookback)
        head = text[:hard]
        position = head.rfind(" ", floor)
        split = position if position > floor else min(hard, len(text))
        return split, True
