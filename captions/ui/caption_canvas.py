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


@dataclass
class CaptionLine:
    text: str
    kind: str
    opacity: float = 1.0


@dataclass
class CaptionCue:
    cue_id: int
    source: str
    translation: str


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
        self.source = ""
        self.translation = ""
        self.cue_id = 0
        self.previous_cues: list[CaptionCue] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_style(self, style: SubtitleConfig) -> None:
        self.style = style
        self.update()

    def set_content(
        self,
        source: str | None = None,
        translation: str | None = None,
    ) -> None:
        if source is not None:
            self.source = source
        if translation is not None:
            self.translation = translation
        self.update()

    def set_cue(self, cue_id: int, source: str, translation: str) -> None:
        source = source.strip()
        translation = translation.strip()
        if cue_id != self.cue_id:
            if self.cue_id and (self.source or self.translation):
                self.previous_cues.append(
                    CaptionCue(self.cue_id, self.source, self.translation)
                )
                self.previous_cues = self.previous_cues[-3:]
            self.cue_id = cue_id
        self.source = source
        self.translation = translation
        self.update()

    def clear(self) -> None:
        self.source = self.translation = ""
        self.cue_id = 0
        self.previous_cues.clear()
        self.update()

    def _font(self, kind: str) -> QFont:
        point_size = (
            self.style.source_size if kind == "source" else self.style.translation_size
        )
        font = QFont(self.style.font_family, point_size)
        font.setWeight(QFont.Weight(max(100, min(900, self.style.font_weight))))
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
        mode = self.style.mode
        limit = max(2, min(6, self.style.max_rows))
        current = CaptionCue(self.cue_id, self.source, self.translation)

        if mode == "source":
            rows = [
                (cue.source, "source", self.style.old_opacity)
                for cue in self.previous_cues
                if cue.source
            ]
            if current.source:
                rows.append((current.source, "source", self.style.preview_opacity))
        if mode == "translation":
            rows = [
                (cue.translation, "translation", self.style.old_opacity)
                for cue in self.previous_cues
                if cue.translation
            ]
            if current.translation:
                rows.append(
                    (current.translation, "translation", self.style.preview_opacity)
                )
        if mode == "bilingual":
            current_rows: list[tuple[str, str, float]] = []
            if current.source:
                current_rows.append(
                    (current.source, "source", self.style.preview_opacity)
                )
            if current.translation:
                current_rows.append(
                    (current.translation, "translation", self.style.preview_opacity)
                )
            remaining = max(0, limit - len(current_rows))
            older_groups: list[list[tuple[str, str, float]]] = []
            for cue in reversed(self.previous_cues):
                if remaining <= 0:
                    break
                pair = [
                    (cue.source, "source", self.style.old_opacity),
                    (cue.translation, "translation", self.style.old_opacity),
                ]
                pair = [row for row in pair if row[0]]
                if not pair:
                    continue
                if remaining == 1:
                    translated = next(
                        (row for row in pair if row[1] == "translation"), pair[-1]
                    )
                    older_groups.append([translated])
                    remaining = 0
                else:
                    selected = pair[-remaining:]
                    older_groups.append(selected)
                    remaining -= len(selected)
            rows = [
                row
                for group in reversed(older_groups)
                for row in group
            ] + current_rows

        rows = rows[-limit:]
        visible: list[CaptionLine] = []
        for text, kind, opacity in rows:
            wrapped = self._wrap_text(
                text, self._font(kind), available, kind == "source"
            )
            visible.extend(CaptionLine(line, kind, opacity) for line in wrapped)
        # `max_rows` limits physical display lines only. Recognition,
        # translation, history, and the naturally wrapped text stay unchanged.
        return visible[-limit:]

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
        total_height = 0.0
        for line in lines:
            font = self._font(line.kind)
            metrics = QFontMetricsF(font)
            text = line.text
            width = min(available, metrics.horizontalAdvance(text))
            height = metrics.height() * self.style.line_height
            layouts.append((line, font, text, width, height))
            total_height += height
        y = self.height() - padding - total_height
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
            baseline = y + (height - metrics.height()) / 2 + metrics.ascent()
            bounds = QRectF(x - 8, y + 1, width + 16, height - 2)
            block_bounds = bounds if block_bounds is None else block_bounds.united(bounds)
            positioned.append((line, font, text, x, baseline, bounds))
            y += height
        if self.style.background == "block" and block_bounds is not None:
            painter.setOpacity(1.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(block_bounds.adjusted(-3, -4, 3, 4), 8, 8)
        for line, font, text, x, baseline, bounds in positioned:
            if self.style.background == "line":
                painter.setOpacity(line.opacity)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(background)
                painter.drawRoundedRect(bounds, 6, 6)
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
