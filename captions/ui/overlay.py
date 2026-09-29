from __future__ import annotations

import copy

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from captions.core.settings import AppConfig
from captions.core.overlay_layout import Bounds, place_overlay
from captions.ui.caption_canvas import CaptionCanvas


class OverlayWindow(QWidget):
    geometry_changed = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._capturing = False
        self._screen = None
        self._laying_out = False
        self._drag_origin: QPoint | None = None
        self._drag_geometry = None
        self.setWindowTitle("实时字幕")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = CaptionCanvas(config.subtitle, self)
        layout.addWidget(self.canvas)
        self.canvas.content_changed.connect(self.refresh_layout)
        self.set_locked(config.window.locked)
        self.windowHandle().screenChanged.connect(self._screen_changed)
        QApplication.instance().screenRemoved.connect(self._screen_removed)

    def restore_placement(self) -> None:
        target = next((s for s in QApplication.screens()
                       if s.name() == self.config.window.screen_name), None)
        if target is None:
            target = QApplication.screenAt(QPoint(self.config.window.x, self.config.window.y))
        self._screen_changed(target or QApplication.primaryScreen())

    def _screen_changed(self, screen) -> None:
        if screen is None or self._laying_out:
            return
        if self._screen is not screen:
            if self._screen in QApplication.screens():
                self._screen.availableGeometryChanged.disconnect(self.refresh_layout)
            self._screen = screen
            screen.availableGeometryChanged.connect(self.refresh_layout)
        self.config.window.screen_name = screen.name()
        self.refresh_layout()

    def _screen_removed(self, screen) -> None:
        if self._screen is screen:
            self._screen = None
            self._screen_changed(QApplication.primaryScreen())

    def refresh_layout(self, *args, snap: bool = False) -> None:
        if self._screen is None or self._laying_out:
            return
        self._laying_out = True
        try:
            area = self._screen.availableGeometry()
            screen = Bounds(area.x(), area.y(), area.width(), area.height())
            window = self.config.window
            width = round(screen.width * window.width_percent / 100)
            height = self.canvas.preferred_height(width, round(screen.height * .4))
            placed = place_overlay(screen, window.width_percent, height,
                                   window.center_x_ratio, window.bottom_ratio, snap=snap)
            self.setGeometry(placed.x, placed.y, placed.width, placed.height)
            if self._drag_origin is not None:
                window.center_x_ratio = (placed.x + placed.width / 2 - screen.x) / screen.width
                window.bottom_ratio = (screen.y + screen.height - placed.y - placed.height) / screen.height
        finally:
            self._laying_out = False

    def set_capturing(self, value: bool) -> None:
        self._capturing = value

    def set_mode(self, mode: str) -> None:
        self.config.subtitle.mode = mode
        self.canvas.set_style(self.config.subtitle)

    def set_display_mode(self, mode: str) -> None:
        style = copy.copy(self.config.subtitle)
        style.mode = mode
        self.canvas.set_style(style)

    def set_locked(self, locked: bool) -> None:
        self.config.window.locked = locked
        self._drag_origin = self._drag_geometry = None
        self.unsetCursor()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, locked)
        self.show()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self.config.window.locked:
            return super().mousePressEvent(event)
        self._drag_origin = event.globalPosition().toPoint()
        self._drag_geometry = self.geometry()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_origin is not None and self._drag_geometry is not None:
            position = event.globalPosition().toPoint()
            delta = position - self._drag_origin
            screen = QApplication.screenAt(position) or self._screen
            if screen is not None:
                area = screen.availableGeometry()
                original = self._drag_geometry
                self.config.window.center_x_ratio = (
                    original.x() + original.width() / 2 + delta.x() - area.x()
                ) / area.width()
                self.config.window.bottom_ratio = (
                    area.y() + area.height() - original.y() - original.height() - delta.y()
                ) / area.height()
                self._screen_changed(screen)
                self.refresh_layout(snap=True)
            event.accept()
            return
        if not self.config.window.locked:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_origin = self._drag_geometry = None
        self.geometry_changed.emit()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.unsetCursor()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.geometry_changed.emit()
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()
