from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QComboBox, QColorDialog, QDoubleSpinBox, QFontComboBox,
    QGroupBox, QPushButton, QPlainTextEdit, QSpinBox, QStyle, QStyleOptionGroupBox,
    QStyledItemDelegate, QStyleOptionViewItem, QToolButton, QVBoxLayout, QWidget,
)
from captions.core.prompt_template import PROMPT_PLACEHOLDER_PATTERN


BACKEND_DELETE_ROLE = int(Qt.ItemDataRole.UserRole) + 1


BACKEND_SEPARATOR_ROLE = int(Qt.ItemDataRole.UserRole) + 2


BACKEND_DELETE_WIDTH = 32


class PromptTemplateHighlighter(QSyntaxHighlighter):
    def __init__(self, document, palette) -> None:
        super().__init__(document)
        self.placeholder_format = QTextCharFormat()
        self.placeholder_format.setForeground(palette.highlight().color())
        self.placeholder_format.setFontWeight(QFont.Weight.DemiBold)

    def set_enabled_palette(self, enabled: bool, palette) -> None:
        color = palette.highlight().color() if enabled else palette.mid().color()
        self.placeholder_format.setForeground(color)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for match in PROMPT_PLACEHOLDER_PATTERN.finditer(text):
            self.setFormat(
                match.start(),
                match.end() - match.start(),
                self.placeholder_format,
            )


class PromptTemplateEdit(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QPlainTextEdit { color:palette(text); background-color:palette(base); }"
            "QPlainTextEdit:disabled { color:palette(mid); }"
        )
        self.highlighter = PromptTemplateHighlighter(
            self.document(),
            self.palette(),
        )

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange and hasattr(self, "highlighter"):
            self.highlighter.set_enabled_palette(self.isEnabled(), self.palette())


class TitleActionGroupBox(QGroupBox):
    actionTriggered = Signal()
    actionToggled = Signal(bool)

    def __init__(
        self,
        title: str,
        action_text: str,
        parent=None,
        *,
        unchecked_action_text: str = "",
    ) -> None:
        super().__init__(title, parent)
        self._checked_action_text = action_text
        self._unchecked_action_text = unchecked_action_text
        self.action_button = QToolButton(self)
        self.action_button.setText(action_text)
        self.action_button.setAutoRaise(True)
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        if unchecked_action_text:
            self.action_button.setCheckable(True)
            self.action_button.setChecked(True)
            self.action_button.setStyleSheet(
                "QToolButton { border:0; padding:0; margin:0; "
                "background:palette(window); }"
                "QToolButton:checked { color:palette(text); }"
                "QToolButton:!checked { color:palette(text); }"
                "QToolButton:hover { color:palette(highlight); }"
            )
            self.action_button.toggled.connect(self._action_toggled)
        else:
            self.action_button.setStyleSheet(
                "QToolButton { border:0; padding:0; margin:0; "
                "background:palette(window); color:palette(text); }"
                "QToolButton:hover { color:palette(highlight); }"
            )
            self.action_button.clicked.connect(self.actionTriggered)

    def set_content_enabled(self, enabled: bool) -> None:
        layout = self.layout()
        if layout is None:
            return
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if widget is not None:
                widget.setEnabled(enabled)

    def _action_toggled(self, checked: bool) -> None:
        self.action_button.setText(
            self._checked_action_text if checked else self._unchecked_action_text
        )
        self._position_action()
        self.actionToggled.emit(checked)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_action()

    def _position_action(self) -> None:
        option = QStyleOptionGroupBox()
        self.initStyleOption(option)
        title_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_GroupBox,
            option,
            QStyle.SubControl.SC_GroupBoxLabel,
            self,
        )
        title_width = self.fontMetrics().horizontalAdvance(self.title())
        title_gap = max(0, title_rect.width() - title_width)
        text_width = self.action_button.fontMetrics().horizontalAdvance(
            self.action_button.text()
        )
        width = text_width + title_gap
        height = max(title_rect.height(), self.action_button.fontMetrics().height())
        self.action_button.setGeometry(
            max(0, self.width() - width - 12),
            title_rect.y(),
            width,
            height,
        )


def _forward_wheel_to_page(widget: QWidget, event) -> None:
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QAbstractScrollArea):
        parent = parent.parentWidget()
    if parent is None:
        event.ignore()
        return
    QApplication.sendEvent(parent.viewport(), event)


class WheelSafeComboBox(QComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)


class BackendItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        if index.data(BACKEND_SEPARATOR_ROLE):
            painter.save()
            painter.setPen(option.palette.mid().color())
            y = option.rect.center().y()
            painter.drawLine(option.rect.left() + 8, y, option.rect.right() - 8, y)
            painter.restore()
            return
        item_option = QStyleOptionViewItem(option)
        if index.data(BACKEND_DELETE_ROLE):
            item_option.rect = option.rect.adjusted(0, 0, -BACKEND_DELETE_WIDTH, 0)
        super().paint(painter, item_option, index)
        if not index.data(BACKEND_DELETE_ROLE):
            return
        delete_rect = QRect(
            option.rect.right() - BACKEND_DELETE_WIDTH + 1,
            option.rect.top(),
            BACKEND_DELETE_WIDTH,
            option.rect.height(),
        )
        painter.save()
        painter.setPen(option.palette.text().color())
        painter.drawText(delete_rect, Qt.AlignmentFlag.AlignCenter, "×")
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        if index.data(BACKEND_SEPARATOR_ROLE):
            return QSize(super().sizeHint(option, index).width(), 9)
        return super().sizeHint(option, index)


class BackendComboBox(WheelSafeComboBox):
    delete_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(BackendItemDelegate(self))
        self.view().viewport().installEventFilter(self)

    def set_item_deletable(self, index: int, deletable: bool) -> None:
        self.setItemData(index, deletable, BACKEND_DELETE_ROLE)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.view().viewport() and event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
        }:
            point = event.position().toPoint()
            index = self.view().indexAt(point)
            if index.isValid() and index.data(BACKEND_DELETE_ROLE):
                rect = self.view().visualRect(index)
                if point.x() >= rect.right() - BACKEND_DELETE_WIDTH + 1:
                    if event.type() == QEvent.Type.MouseButtonRelease:
                        backend = str(index.data(Qt.ItemDataRole.UserRole))
                        self.hidePopup()
                        self.delete_requested.emit(backend)
                    return True
        return super().eventFilter(watched, event)


class WheelSafeSpinBox(QSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        if event.reason() == Qt.FocusReason.MouseFocusReason:
            QTimer.singleShot(0, self.selectAll)


class WheelSafeDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        if event.reason() == Qt.FocusReason.MouseFocusReason:
            QTimer.singleShot(0, self.selectAll)


class WheelSafeFontComboBox(QFontComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)


class ExpandableSection(QWidget):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._expanded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.toggle.setStyleSheet("font-weight:600;padding:4px 0")
        self.toggle.clicked.connect(self._toggle_expanded)
        layout.addWidget(self.toggle)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self.body.hide()
        layout.addWidget(self.body)

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802
        self.body_layout.addWidget(widget)

    def _toggle_expanded(self) -> None:
        self._set_expanded(not self._expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.body.setVisible(expanded)


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.value = "#ffffff"
        self.clicked.connect(self.choose)

    def set_color(self, value: str) -> None:
        self.value = value
        self.setText(value)
        color = QColor(value)
        if color.isValid():
            foreground = "#000" if color.lightness() > 150 else "#fff"
            self.setStyleSheet(f"background:{value};color:{foreground};padding:5px")
        self.color_changed.emit(value)

    def choose(self) -> None:
        color = QColorDialog.getColor(QColor(self.value), self)
        if color.isValid():
            self.set_color(color.name(QColor.NameFormat.HexArgb))
