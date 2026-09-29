from __future__ import annotations


_TRAILING_MARKS = " .?!。？！…,，;；:：\"'”’»」』】）》)]}"


def source_extends_preview(preview_source: str, current_source: str) -> bool:
    """Allow a translated prefix, but not text removed by an ASR revision/split."""
    previous = " ".join(preview_source.split()).rstrip(_TRAILING_MARKS).casefold()
    current = " ".join(current_source.split()).rstrip(_TRAILING_MARKS).casefold()
    return bool(previous) and current.startswith(previous)
