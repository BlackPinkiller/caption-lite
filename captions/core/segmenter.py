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

_TERMINAL_PUNCTUATION = re.compile(r"[。？！…]|[.?!]+")
_WEAK_PUNCTUATION = re.compile(r"[,，、;；:：]")
_TERMINAL_MARKS = ".?!。？！…"
_WEAK_MARKS = ",，、;；:："
_CLOSING_PUNCTUATION = frozenset("\"'”’»」』】）》〕〗〙〛)]}")


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
        punctuation_mode: str = "sentence",
        min_commit_chars: int = 4,
    ) -> None:
        self.max_chars = max_chars
        self.max_seconds = max_seconds
        self.split_lookback_chars = split_lookback_chars
        self.split_lookahead_chars = split_lookahead_chars
        self.punctuation_mode = (
            punctuation_mode
            if punctuation_mode in {"off", "sentence", "all"}
            else "sentence"
        )
        self.min_commit_chars = max(1, int(min_commit_chars))
        self.reset()

    def reset(self) -> None:
        self._raw = ""
        self._consumed = 0
        self._started = 0.0
        self._pending_weak_boundary = ""

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
            self.reset()
            return SegmentUpdate("")
        if self._started == 0:
            self._started = now
        if self._consumed and not raw.startswith(self._raw[: self._consumed]):
            reconciled = self._reconcile_consumed(
                self._raw[: self._consumed],
                raw,
            )
            self._pending_weak_boundary = ""
            if reconciled is None:
                self.reset()
                self._started = now
            else:
                self._consumed = reconciled
        self._raw = raw
        commits: list[SegmentCommit] = []

        active = self.active
        if self.punctuation_mode != "off":
            while True:
                boundary = self._next_boundary(active)
                if boundary is None:
                    break
                committed = active[:boundary].strip()
                self._consumed = self._active_start() + boundary
                self._started = now
                self._pending_weak_boundary = ""
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

        while len(active) > self.max_chars:
            decision = self._window_split(active)
            if decision is None:
                break
            split, forced = decision
            committed = active[:split].strip()
            self._consumed = self._active_start() + split
            self._started = now
            commits.append(SegmentCommit(committed, forced))
            active = self.active
        return SegmentUpdate(self.active, tuple(commits))

    def flush(self, forced: bool = False) -> SegmentUpdate:
        active = self.active
        self.reset()
        if active:
            return SegmentUpdate("", (SegmentCommit(active, forced),))
        return SegmentUpdate("")

    def _next_boundary(self, text: str) -> int | None:
        floor = max(1, self.min_commit_chars)
        if any(mark in text for mark in _TERMINAL_MARKS):
            for match in _TERMINAL_PUNCTUATION.finditer(text):
                if self._is_abbreviation(text, match.start()):
                    continue
                end = self._terminal_boundary_end(text, match)
                if end is None:
                    continue
                if len(text[:end].strip()) < floor:
                    continue
                self._pending_weak_boundary = ""
                return end

        if self.punctuation_mode == "all" and any(
            mark in text for mark in _WEAK_MARKS
        ):
            for match in _WEAK_PUNCTUATION.finditer(text):
                end = self._with_closing_punctuation(text, match.end())
                if len(text[:end].strip()) < floor:
                    continue
                if self._is_numeric_separator(text, match.start(), match.end()):
                    continue
                candidate = text[:end].strip()
                stable = candidate == self._pending_weak_boundary
                self._pending_weak_boundary = candidate
                if stable and text[end:].strip():
                    self._pending_weak_boundary = ""
                    return end
                return None
        self._pending_weak_boundary = ""
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

    @staticmethod
    def _with_closing_punctuation(text: str, end: int) -> int:
        while end < len(text) and text[end] in _CLOSING_PUNCTUATION:
            end += 1
        return end

    def _terminal_boundary_end(
        self,
        text: str,
        match: re.Match[str],
    ) -> int | None:
        end = self._with_closing_punctuation(text, match.end())
        if text[match.start()] in ".?!" and end < len(text):
            if not text[end].isspace():
                return None
        return end

    @staticmethod
    def _is_numeric_separator(text: str, start: int, end: int) -> bool:
        return (
            start > 0
            and end < len(text)
            and text[start - 1].isdigit()
            and text[end].isdigit()
        )

    def _window_split(self, text: str) -> tuple[int, bool] | None:
        soft = max(1, self.max_chars)
        lookback = max(0, self.split_lookback_chars)
        lookahead = max(0, self.split_lookahead_chars)
        hard = soft + lookahead
        start = max(0, soft - lookback)
        end = min(len(text), hard)
        punctuation: list[tuple[int, int]] = []
        if self.punctuation_mode != "off":
            window = text[start:end]
            if any(mark in window for mark in _TERMINAL_MARKS):
                for match in _TERMINAL_PUNCTUATION.finditer(text, start, end):
                    if self._is_abbreviation(text, match.start()):
                        continue
                    boundary = self._terminal_boundary_end(text, match)
                    if boundary is not None:
                        punctuation.append((match.start(), boundary))
            if self.punctuation_mode == "all" and any(
                mark in window for mark in _WEAK_MARKS
            ):
                for match in _WEAK_PUNCTUATION.finditer(text, start, end):
                    if self._is_numeric_separator(text, match.start(), match.end()):
                        continue
                    punctuation.append(
                        (
                            match.start(),
                            self._with_closing_punctuation(text, match.end()),
                        )
                    )
            punctuation.sort()
        if punctuation:
            after_soft = [boundary for _, boundary in punctuation if boundary >= soft]
            selected = after_soft[0] if after_soft else punctuation[-1][1]
            return selected, False
        if len(text) < hard:
            return None
        floor = max(0, hard - lookback)
        head = text[:hard]
        position = head.rfind(" ", floor)
        split = position if position > floor else min(hard, len(text))
        return split, True

    @staticmethod
    def _reconcile_consumed(previous_prefix: str, revised: str) -> int | None:
        previous = previous_prefix.rstrip()
        if not previous:
            return None
        distances = list(range(len(revised) + 1))
        for old_index, old_char in enumerate(previous):
            following = [old_index + 1]
            for new_index, new_char in enumerate(revised):
                substitution = distances[new_index] + (old_char != new_char)
                deletion = distances[new_index + 1] + 1
                insertion = following[new_index] + 1
                following.append(min(substitution, deletion, insertion))
            distances = following
        best_index = min(
            range(len(distances)),
            key=lambda index: (distances[index], abs(index - len(previous))),
        )
        allowed_changes = max(4, len(previous) // 3)
        distance = distances[best_index]
        if (
            best_index == 0
            or distance >= max(len(previous), best_index)
            or distance > allowed_changes
        ):
            return None
        return best_index
