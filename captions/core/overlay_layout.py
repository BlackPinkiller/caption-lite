"""Screen-relative subtitle placement in logical coordinates, without GUI APIs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


def place_overlay(
    screen: Bounds, width_percent: int, height: int,
    center_x: float, bottom: float, *, snap: bool = False,
) -> Bounds:
    width = round(screen.width * max(30, min(90, width_percent)) / 100)
    height = min(height, round(screen.height * .9))
    center = screen.x + center_x * screen.width
    screen_center = screen.x + screen.width / 2
    if snap and abs(center - screen_center) <= 12:
        center = screen_center
    left = screen.x + round(screen.width * .05)
    right = screen.x + screen.width - round(screen.width * .05)
    top = screen.y + round(screen.height * .05)
    lower = screen.y + screen.height - round(screen.height * .05)
    x = max(left, min(right - width, round(center - width / 2)))
    y = max(top, min(lower - height, round(screen.y + screen.height * (1 - bottom) - height)))
    return Bounds(x, y, width, height)
