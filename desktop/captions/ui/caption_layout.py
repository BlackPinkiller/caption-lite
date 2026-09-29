"""Select complete wrapped lines for the available drawing height."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass
class CaptionLine:
    text: str
    kind: str
    opacity: float = 1.0
    current: bool = False


def lines_height(lines: list[CaptionLine], heights: dict[str, float], spacing: float) -> float:
    return sum(heights[line.kind] for line in lines) + spacing * max(0, len(lines) - 1)


def fit_lines(lines: list[CaptionLine], heights: dict[str, float], spacing: float,
              available: float) -> list[CaptionLine]:
    lines = list(lines)
    truncated = set()
    while lines and lines_height(lines, heights, spacing) > available:
        old = next((i for i, line in enumerate(lines) if not line.current), None)
        if old is not None:
            lines.pop(old)
            continue
        counts = {kind: sum(line.kind == kind for line in lines) for kind in heights}
        candidates = [kind for kind, count in counts.items() if count > 1]
        if candidates:
            kind = max(candidates, key=lambda value: counts[value] * heights[value])
            index = next(i for i, line in enumerate(lines) if line.kind == kind)
            truncated.add(kind)
            lines.pop(index)
        else:
            # Extremely small previews cannot fit even one line per language.
            lines.pop(0)
    for kind in truncated:
        index = next((i for i, line in enumerate(lines) if line.kind == kind), None)
        if index is not None:
            lines[index] = replace(lines[index], text="…" + lines[index].text)
    return lines
