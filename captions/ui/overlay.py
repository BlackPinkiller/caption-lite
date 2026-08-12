from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from captions.config import AppConfig
from captions.ui.caption_canvas import CaptionCanvas


class OverlayWindow(QWidget):
    geometry_changed = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._capturing = False
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None
        self.setWindowTitle("实时字幕")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = CaptionCanvas(config.subtitle, self)
        layout.addWidget(self.canvas)
        self.set_locked(config.window.locked)

    def set_capturing(self, value: bool) -> None:
        self._capturing = value

    def set_mode(self, mode: str) -> None:
        self.config.subtitle.mode = mode
        self.canvas.set_style(self.config.subtitle)

    def set_locked(self, locked: bool) -> None:
        self.config.window.locked = locked
        self.unsetCursor()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, locked)
        self.show()

    def _resize_edges(self, position: QPoint) -> Qt.Edges:
        margin = 9
        edges = Qt.Edge(0)
        if position.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif position.x() >= self.width() - margin:
            edges |= Qt.Edge.RightEdge
        if position.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif position.y() >= self.height() - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _update_cursor(self, position: QPoint) -> None:
        if self.config.window.locked:
            return
        edges = self._resize_edges(position)
        if edges in (
            Qt.Edge.LeftEdge | Qt.Edge.TopEdge,
            Qt.Edge.RightEdge | Qt.Edge.BottomEdge,
        ):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (
            Qt.Edge.RightEdge | Qt.Edge.TopEdge,
            Qt.Edge.LeftEdge | Qt.Edge.BottomEdge,
        ):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self.config.window.locked:
            return super().mousePressEvent(event)
        position = event.position().toPoint()
        edges = self._resize_edges(position)
        handle = self.windowHandle()
        if edges and handle is not None and handle.startSystemResize(edges):
            event.accept()
            return
        if handle is not None and handle.startSystemMove():
            event.accept()
            return
        self._drag_origin = event.globalPosition().toPoint()
        self._window_origin = self.pos()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_origin is not None and self._window_origin is not None:
            self.move(self._window_origin + event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        self._update_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_origin = self._window_origin = None
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
