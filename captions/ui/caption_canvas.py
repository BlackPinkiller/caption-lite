from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from captions.config import SubtitleConfig
from captions.core.caption_state import CaptionCue, CaptionState


@dataclass
class CaptionLine:
    text: str
    kind: str
    opacity: float = 1.0


def parse_color(value: str) -> QColor:
    color = QColor(value)
    if color.isValid():
        return color
    match = re.fullmatch(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)",
        value,
    )
    if not match:
        return QColor(0, 0, 0, 158)
    red, green, blue = map(int, match.group(1, 2, 3))
    alpha_text = match.group(4)
    alpha = 255 if alpha_text is None else round(float(alpha_text) * 255)
    return QColor(red, green, blue, max(0, min(255, alpha)))


class CaptionCanvas(QWidget):
    def __init__(
        self,
        style: SubtitleConfig,
        parent: QWidget | None = None,
        *,
        preview: bool = False,
    ) -> None:
        super().__init__(parent)
        self.style = style
        self.preview = preview
        self.state = CaptionState()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    @property
    def source(self) -> str:
        return self.state.source

    @source.setter
    def source(self, value: str) -> None:
        self.state.source = value

    @property
    def translation(self) -> str:
        return self.state.translation

    @translation.setter
    def translation(self, value: str) -> None:
        self.state.translation = value

    @property
    def cue_id(self) -> int:
        return self.state.cue_id

    @cue_id.setter
    def cue_id(self, value: int) -> None:
        self.state.cue_id = value

    @property
    def previous_cues(self) -> list[CaptionCue]:
        return self.state.previous_cues

    @previous_cues.setter
    def previous_cues(self, value: list[CaptionCue]) -> None:
        self.state.previous_cues = value

    def set_style(self, style: SubtitleConfig) -> None:
        self.style = style
        self.update()

    def set_content(
        self,
        source: str | None = None,
        translation: str | None = None,
    ) -> None:
        self.state.set_content(source, translation)
        self.update()

    def set_cue(self, cue_id: int, source: str, translation: str) -> None:
        self.state.set_cue(cue_id, source, translation)
        self.update()

    def set_translation(self, cue_id: int, translation: str) -> bool:
        if self.state.set_translation(cue_id, translation):
            self.update()
            return True
        return False

    def clear(self) -> None:
        self.state.clear()
        self.update()

    def _font(self, kind: str) -> QFont:
        pixel_size = (
            self.style.source_size if kind == "source" else self.style.translation_size
        )
        font = QFont(self.style.font_family)
        font.setPixelSize(pixel_size)
        font.setWeight(QFont.Weight(600))
        return font

    @staticmethod
    def _wrap_text(text: str, font: QFont, width: float, words: bool) -> list[str]:
        text = " ".join(text.split()) if words else "".join(text.splitlines())
        if not text:
            return []
        metrics = QFontMetricsF(font)
        units = re.findall(r"\S+\s*", text) if words else list(text)
        lines: list[str] = []
        current = ""
        for unit in units:
            candidate = current + unit
            if current and metrics.horizontalAdvance(candidate.rstrip()) > width:
                lines.append(current.rstrip())
                current = ""
            if metrics.horizontalAdvance(unit.rstrip()) <= width:
                current += unit
                continue
            for character in unit:
                candidate = current + character
                if current and metrics.horizontalAdvance(candidate.rstrip()) > width:
                    lines.append(current.rstrip())
                    current = character
                else:
                    current = candidate
        if current.strip():
            lines.append(current.rstrip())
        return lines

    def _visible_lines(self, available: float) -> list[CaptionLine]:
        visible: list[CaptionLine] = []
        entries = self.state.visible_entries(
            self.style.mode,
            self.style.max_sentences,
            self.style.old_opacity,
            self.style.preview_opacity,
        )
        for entry in entries:
            wrapped = self._wrap_text(
                entry.text,
                self._font(entry.kind),
                available,
                entry.kind == "source",
            )
            visible.extend(
                CaptionLine(line, entry.kind, entry.opacity) for line in wrapped
            )
        return visible

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self.preview:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#64748b"))
            painter.drawRoundedRect(self.rect(), 8, 8)
        padding = self.style.padding
        available = max(40.0, self.width() - padding * 2)
        lines = self._visible_lines(available - self.style.outline_width * 4)
        if not lines:
            return
        layouts: list[tuple[CaptionLine, QFont, str, float, float]] = []
        line_background_padding_y = (
            float(self.style.background_padding_y)
            if self.style.background == "line"
            else 0.0
        )
        block_background_padding_y = (
            float(self.style.background_padding_y)
            if self.style.background == "block"
            else 0.0
        )
        for line in lines:
            font = self._font(line.kind)
            metrics = QFontMetricsF(font)
            text = line.text
            width = min(available, metrics.horizontalAdvance(text))
            height = metrics.height() + line_background_padding_y * 2
            layouts.append((line, font, text, width, height))
        spacing = float(self.style.line_spacing)
        total_height = sum(layout[4] for layout in layouts)
        total_height += spacing * max(0, len(layouts) - 1)
        total_height += block_background_padding_y * 2
        y = self.height() - padding - total_height + block_background_padding_y
        block_bounds: QRectF | None = None
        background = parse_color(self.style.background_color)
        text_color = parse_color(self.style.text_color)
        outline = parse_color(self.style.outline_color)
        positioned: list[tuple[CaptionLine, QFont, str, float, float, QRectF]] = []
        for line, font, text, width, height in layouts:
            if self.style.align == "left":
                x = float(padding)
            elif self.style.align == "right":
                x = self.width() - padding - width
            else:
                x = (self.width() - width) / 2
            metrics = QFontMetricsF(font)
            baseline = y + line_background_padding_y + metrics.ascent()
            bounds = QRectF(x - 8, y, width + 16, height)
            block_bounds = bounds if block_bounds is None else block_bounds.united(bounds)
            positioned.append((line, font, text, x, baseline, bounds))
            y += height + spacing
        if self.style.background == "block" and block_bounds is not None:
            painter.setOpacity(1.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            radius = float(self.style.background_radius)
            painter.drawRoundedRect(
                block_bounds.adjusted(
                    -3,
                    -block_background_padding_y,
                    3,
                    block_background_padding_y,
                ),
                radius,
                radius,
            )
        for line, font, text, x, baseline, bounds in positioned:
            if self.style.background == "line":
                painter.setOpacity(line.opacity)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(background)
                radius = float(self.style.background_radius)
                painter.drawRoundedRect(bounds, radius, radius)
            path = QPainterPath()
            path.addText(QPointF(x, baseline), font, text)
            painter.setOpacity(line.opacity)
            if self.style.shadow:
                shadow_path = QPainterPath(path)
                shadow_path.translate(2, 3)
                painter.setPen(QPen(QColor(0, 0, 0, 170), self.style.outline_width + 3))
                painter.setBrush(QColor(0, 0, 0, 170))
                painter.drawPath(shadow_path)
            painter.setPen(
                QPen(
                    outline,
                    self.style.outline_width * 2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(text_color)
            painter.drawPath(path)
