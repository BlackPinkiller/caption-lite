from __future__ import annotations

import re
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentCommit:
    text: str
    forced: bool = False


@dataclass(frozen=True)
class SegmentUpdate:
    active: str
    commits: tuple[SegmentCommit, ...] = ()


_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "inc",
        "ltd",
        "co",
        "corp",
        "dept",
        "no",
        "fig",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
        "u.s",
        "u.k",
        "ave",
        "blvd",
        "rd",
        "sq",
        "mt",
        "hwy",
    }
)

_TERMINAL_PUNCTUATION = re.compile(r"[。？！]|[.?!](?=\s|$)")


def should_commit_endpoint(
    text: str,
    *,
    vad_endpoint: bool,
    asr_endpoint: bool,
    silence_min_chars: int,
) -> bool:
    if asr_endpoint:
        return True
    return vad_endpoint and len(text.strip()) >= max(1, silence_min_chars)


class Segmenter:
    """Separates semantic commits from the recognizer's cumulative text."""

    def __init__(
        self,
        max_chars: int = 160,
        max_seconds: float = 20.0,
        split_lookback_chars: int = 32,
        split_lookahead_chars: int = 160,
        split_punctuation: bool = True,
        min_commit_chars: int = 4,
    ) -> None:
        self.max_chars = max_chars
        self.max_seconds = max_seconds
        self.split_lookback_chars = split_lookback_chars
        self.split_lookahead_chars = split_lookahead_chars
        self.split_punctuation = split_punctuation
        self.min_commit_chars = max(1, int(min_commit_chars))
        self.reset()

    def reset(self) -> None:
        self._raw = ""
        self._consumed = 0
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
        commits: list[SegmentCommit] = []

        active = self.active
        if self.split_punctuation:
            while True:
                boundary = self._next_boundary(active)
                if boundary is None:
                    break
                committed = active[:boundary].strip()
                self._consumed = self._active_start() + boundary
                self._started = now
                commits.append(SegmentCommit(committed))
                active = self.active

        active = self.active
        if not active:
            return SegmentUpdate("", tuple(commits))

        if self.max_seconds > 0 and now - self._started >= self.max_seconds:
            committed = active.strip()
            self._consumed = self._active_start() + len(active)
            self._started = now
            commits.append(SegmentCommit(committed, True))
            return SegmentUpdate(self.active, tuple(commits))

        if len(active) > self.max_chars:
            decision = self._window_split(active)
            if decision is not None:
                split, forced = decision
                committed = active[:split].strip()
                self._consumed = self._active_start() + split
                self._started = now
                commits.append(SegmentCommit(committed, forced))
        return SegmentUpdate(self.active, tuple(commits))

    def flush(self, forced: bool = False) -> SegmentUpdate:
        active = self.active
        self.reset()
        if active:
            return SegmentUpdate("", (SegmentCommit(active, forced),))
        return SegmentUpdate("")

    def _next_boundary(self, text: str) -> int | None:
        floor = max(1, self.min_commit_chars)
        for match in _TERMINAL_PUNCTUATION.finditer(text):
            if self._is_abbreviation(text, match.start()):
                continue
            end = match.end()
            if len(text[:end].strip()) < floor:
                continue
            return end
        return None

    def _is_abbreviation(self, text: str, pos: int) -> bool:
        if text[pos] != ".":
            return False
        match = re.search(r"([A-Za-z][\w.]*)\s*$", text[:pos])
        if not match:
            return False
        token = match.group(1)
        if len(token) == 1 and token.isupper():
            return True
        if token.isupper() and "." in token:
            return True
        return token.lower() in _ABBREVIATIONS

    def _window_split(self, text: str) -> tuple[int, bool] | None:
        soft = max(1, self.max_chars)
        lookback = max(0, self.split_lookback_chars)
        lookahead = max(0, self.split_lookahead_chars)
        hard = soft + lookahead
        start = max(0, soft - lookback)
        end = min(len(text), hard)
        window = text[start:end]
        punctuation: list[re.Match[str]] = []
        if self.split_punctuation:
            punctuation = [
                match
                for match in _TERMINAL_PUNCTUATION.finditer(window)
                if not self._is_abbreviation(text, start + match.start())
            ]
        if punctuation:
            after_soft = [match for match in punctuation if start + match.end() >= soft]
            selected = after_soft[0] if after_soft else punctuation[-1]
            return start + selected.end(), False
        if len(text) < hard:
            return None
        floor = max(0, hard - lookback)
        head = text[:hard]
        position = head.rfind(" ", floor)
        split = position if position > floor else min(hard, len(text))
        return split, True
