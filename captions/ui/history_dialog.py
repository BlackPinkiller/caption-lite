from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from captions.translation import HistoryRecord

MAX_HISTORY_RECORDS = 5_000
HISTORY_PAGE_SIZE = 200
BACKEND_NAMES = {
    "llama": "Llama",
    "google2": "Google",
    "deepl": "DeepL",
    "off": "仅识别",
}


class HistoryDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("本次字幕历史")
        self.resize(760, 520)
        self.records: list[HistoryRecord] = []
        self._record_ids: list[int] = []
        self._records_by_id: dict[int, HistoryRecord] = {}
        self._next_record_id = 0
        self._loaded_count = HISTORY_PAGE_SIZE
        self.live_source = ""
        self.live_translation = ""
        self.live_translation_source = ""
        self.translation_enabled = True
        self.follow_live = True
        self._rebuilding = False
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(QLabel("显示"))
        self.filter = QComboBox()
        self.filter.addItem("识别 + 翻译", "both")
        self.filter.addItem("仅识别文本", "source")
        self.filter.addItem("仅翻译文本", "translation")
        self.filter.currentIndexChanged.connect(self.refresh)
        tools.addWidget(self.filter)
        self.count_label = QLabel("0 条")
        self.count_label.setStyleSheet("color:#777")
        tools.addWidget(self.count_label)
        tools.addStretch()
        smaller = QPushButton("A−")
        larger = QPushButton("A+")
        smaller.setToolTip("减小历史文字")
        larger.setToolTip("增大历史文字")
        self.clear_button = QPushButton("清空")
        self.clear_button.setToolTip("清空本次已完成的字幕记录")
        smaller.clicked.connect(lambda: self._change_font(-1))
        larger.clicked.connect(lambda: self._change_font(1))
        self.clear_button.clicked.connect(self._confirm_clear)
        tools.addWidget(smaller)
        tools.addWidget(larger)
        tools.addWidget(self.clear_button)
        layout.addLayout(tools)
        self.content = QStackedWidget()
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.list.setSpacing(3)
        self.list.itemDoubleClicked.connect(self._copy_item)
        self._apply_palette()
        scrollbar = self.list.verticalScrollBar()
        scrollbar.setSingleStep(28)
        scrollbar.valueChanged.connect(self._scroll_position_changed)
        scrollbar.rangeChanged.connect(self._scroll_range_changed)
        scrollbar.sliderReleased.connect(self._load_older_if_at_top)
        self.content.addWidget(self.list)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch(1)
        empty_title = QLabel("本次还没有字幕记录")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet("font-size:16px;font-weight:600")
        empty_layout.addWidget(empty_title)
        empty_note = QLabel("识别完成的字幕会自动保留在这里。")
        empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_note.setStyleSheet("color:#777")
        empty_layout.addWidget(empty_note)
        empty_layout.addStretch(1)
        self.content.addWidget(empty)
        self.empty_page = empty
        layout.addWidget(self.content)
        self._default_hint = "双击一条字幕即可复制；向上滚动可查看更早记录。"
        self.hint = QLabel(self._default_hint)
        self.hint.setStyleSheet("color: #777")
        layout.addWidget(self.hint)
        self.copy_feedback_timer = QTimer(self)
        self.copy_feedback_timer.setSingleShot(True)
        self.copy_feedback_timer.setInterval(1800)
        self.copy_feedback_timer.timeout.connect(
            lambda: self.hint.setText(self._default_hint)
        )
        self._update_empty_state()

    def append(self, record: HistoryRecord) -> int:
        record_id = self._store_record(record)
        self._append_record_item(record_id, record)
        return record_id

    def commit_live(self, record: HistoryRecord) -> int:
        if (
            not record.translation
            and self.live_translation
            and self.live_translation_source == record.source
        ):
            record.translation = self.live_translation
        record_id = self._store_record(record)
        self.live_source = ""
        self.live_translation = ""
        self.live_translation_source = ""
        live = self._find_item("live")
        if live is not None:
            self.list.takeItem(self.list.row(live))
        self._append_record_item(record_id, record)
        return record_id

    def _store_record(self, record: HistoryRecord) -> int:
        record_id = self._next_record_id
        self._next_record_id += 1
        self.records.append(record)
        self._record_ids.append(record_id)
        self._records_by_id[record_id] = record
        if len(self.records) > MAX_HISTORY_RECORDS:
            self.records.pop(0)
            expired_id = self._record_ids.pop(0)
            self._records_by_id.pop(expired_id, None)
            expired_item = self._find_item(expired_id)
            if expired_item is not None:
                self.list.takeItem(self.list.row(expired_item))
        return record_id

    def _append_record_item(self, index: int, record: HistoryRecord) -> None:
        item = QListWidgetItem(self._record_text(record))
        item.setData(Qt.ItemDataRole.UserRole, index)
        item.setToolTip("双击复制")
        live = self._find_item("live")
        if live is None:
            self.list.addItem(item)
        else:
            self.list.insertItem(self.list.row(live), item)
        self._reflow_item(item)
        self._trim_rendered_records()
        self._update_empty_state()

    def _trim_rendered_records(self) -> None:
        limit = min(self._loaded_count, len(self.records))
        live_count = 1 if self._find_item("live") is not None else 0
        rendered_records = self.list.count() - live_count
        while rendered_records > limit:
            self.list.takeItem(0)
            rendered_records -= 1

    def update_translation(self, record_id: int, translation: str) -> None:
        record = self._records_by_id.get(record_id)
        if record is not None:
            record.translation = translation
            item = self._find_item(record_id)
            if item is not None:
                item.setText(self._record_text(record))
                self._reflow_item(item)

    def set_live(
        self,
        source: str | None = None,
        translation: str | None = None,
    ) -> None:
        if source is not None:
            self.live_source = source
        if translation is not None:
            self.live_translation = translation
            self.live_translation_source = self.live_source
        item = self._find_item("live")
        if not self.live_source and not self.live_translation:
            if item is not None:
                self.list.takeItem(self.list.row(item))
            self._update_empty_state()
            return
        if item is None:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, "live")
            self._style_live_item(item)
            self.list.addItem(item)
        item.setText(self._live_text())
        self._reflow_item(item)
        self._update_empty_state()

    def clear_live(self) -> None:
        self.live_source = ""
        self.live_translation = ""
        self.live_translation_source = ""
        item = self._find_item("live")
        if item is not None:
            self.list.takeItem(self.list.row(item))
        self._update_empty_state()

    def set_live_translation(self, source: str, translation: str) -> None:
        self.set_live(translation=translation)
        self.live_translation_source = source

    def set_translation_enabled(self, enabled: bool) -> None:
        self.translation_enabled = bool(enabled)
        if not self.translation_enabled:
            self.live_translation = ""
            self.live_translation_source = ""
        live = self._find_item("live")
        if live is not None:
            live.setText(self._live_text())
            self._reflow_item(live)

    def clear(self) -> None:
        self.records.clear()
        self._record_ids.clear()
        self._records_by_id.clear()
        self._loaded_count = HISTORY_PAGE_SIZE
        self.refresh()

    def _confirm_clear(self) -> None:
        if not self.records:
            return
        answer = QMessageBox.question(
            self,
            "清空字幕历史",
            "清空本次已完成的字幕记录？\n当前正在识别的字幕不会受影响。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear()

    def refresh(self) -> None:
        mode = self.filter.currentData() or "both"
        scrollbar = self.list.verticalScrollBar()
        follow_live = self.follow_live
        old_value = scrollbar.value()
        self._rebuilding = True
        self.list.clear()
        start = max(0, len(self.records) - self._loaded_count)
        for record_id, record in zip(
            self._record_ids[start:], self.records[start:], strict=True
        ):
            item = QListWidgetItem(self._record_text(record, mode))
            item.setData(Qt.ItemDataRole.UserRole, record_id)
            item.setToolTip("双击复制")
            self.list.addItem(item)
        if self.live_source or self.live_translation:
            item = QListWidgetItem(self._live_text(mode))
            item.setData(Qt.ItemDataRole.UserRole, "live")
            self._style_live_item(item)
            item.setToolTip("当前实时字幕")
            self.list.addItem(item)
        self._rebuilding = False
        self.follow_live = follow_live
        QTimer.singleShot(0, self._reflow_items)
        QTimer.singleShot(
            0,
            self.list.scrollToBottom
            if follow_live
            else lambda value=old_value: self.list.verticalScrollBar().setValue(value),
        )
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        has_content = bool(self.records or self.live_source or self.live_translation)
        self.content.setCurrentWidget(self.list if has_content else self.empty_page)
        suffix = " · 实时更新中" if self.live_source or self.live_translation else ""
        self.count_label.setText(f"{len(self.records)} 条{suffix}")
        self.clear_button.setEnabled(bool(self.records))

    def _record_text(self, record: HistoryRecord, mode: str | None = None) -> str:
        mode = mode or self.filter.currentData() or "both"
        backend = BACKEND_NAMES.get(record.backend, record.backend)
        parts = [f"{record.time}  ·  {backend}"]
        if record.forced:
            parts[0] += "  ·  强制切分"
        if mode != "translation":
            parts.extend(("", record.source))
        if mode != "source" and record.translation:
            parts.extend(("", record.translation))
        return "\n".join(parts)

    def _live_text(self, mode: str | None = None) -> str:
        mode = mode or self.filter.currentData() or "both"
        state = "正在识别与翻译" if self.translation_enabled else "正在识别"
        parts = [f"实时  ·  {state}"]
        if mode != "translation" and self.live_source:
            parts.extend(("", self.live_source))
        if mode != "source" and self.live_translation:
            parts.extend(("", self.live_translation))
        return "\n".join(parts)

    def _find_item(self, identity: int | str) -> QListWidgetItem | None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == identity:
                return item
        return None

    def _scroll_position_changed(self, value: int) -> None:
        if self._rebuilding:
            return
        scrollbar = self.list.verticalScrollBar()
        was_following = self.follow_live
        self.follow_live = scrollbar.maximum() - value <= 4
        if not was_following and value <= 4:
            self._load_older()

    def _load_older_if_at_top(self) -> None:
        scrollbar = self.list.verticalScrollBar()
        if not self.follow_live and scrollbar.value() <= 4:
            self._load_older()

    def _load_older(self) -> None:
        if self._rebuilding or self._loaded_count >= len(self.records):
            return
        old_start = max(0, len(self.records) - self._loaded_count)
        new_loaded_count = min(len(self.records), self._loaded_count + HISTORY_PAGE_SIZE)
        new_start = len(self.records) - new_loaded_count
        scrollbar = self.list.verticalScrollBar()
        old_value = scrollbar.value()
        old_maximum = scrollbar.maximum()
        mode = self.filter.currentData() or "both"
        self._rebuilding = True
        for row, position in enumerate(range(new_start, old_start)):
            item = QListWidgetItem(self._record_text(self.records[position], mode))
            item.setData(Qt.ItemDataRole.UserRole, self._record_ids[position])
            item.setToolTip("双击复制")
            self.list.insertItem(row, item)
            self._reflow_item(item)
        self._loaded_count = new_loaded_count

        def restore_position() -> None:
            scrollbar.setValue(old_value + scrollbar.maximum() - old_maximum)
            self.follow_live = False
            self._rebuilding = False

        QTimer.singleShot(0, restore_position)

    def _scroll_range_changed(self, minimum: int, maximum: int) -> None:
        if self._rebuilding or not self.follow_live:
            return
        QTimer.singleShot(0, self.list.scrollToBottom)

    @staticmethod
    def _mix_color(base: QColor, accent: QColor, amount: float) -> QColor:
        keep = 1.0 - amount
        return QColor(
            round(base.red() * keep + accent.red() * amount),
            round(base.green() * keep + accent.green() * amount),
            round(base.blue() * keep + accent.blue() * amount),
        )

    def _style_live_item(self, item: QListWidgetItem) -> None:
        palette = getattr(self, "_history_palette", self.list.palette())
        item.setBackground(
            self._mix_color(
                palette.color(QPalette.ColorRole.Base),
                palette.color(QPalette.ColorRole.Highlight),
                0.14,
            )
        )
        item.setForeground(palette.color(QPalette.ColorRole.Text))

    def _apply_palette(self) -> None:
        palette = self.list.palette()
        self._history_palette = QPalette(palette)
        base = palette.color(QPalette.ColorRole.Base)
        highlight = palette.color(QPalette.ColorRole.Highlight)
        text = palette.color(QPalette.ColorRole.Text)
        hover = self._mix_color(base, highlight, 0.18)
        selected = self._mix_color(base, highlight, 0.28)
        self.list.setStyleSheet(
            "QListWidget::item:hover {"
            f"background-color:{hover.name()};color:{text.name()};"
            "}"
            "QListWidget::item:selected {"
            f"background-color:{selected.name()};color:{text.name()};"
            "}"
        )
        live = self._find_item("live")
        if live is not None:
            self._style_live_item(live)

    def _copy_item(self, item: QListWidgetItem) -> None:
        QGuiApplication.clipboard().setText(item.text())
        self.hint.setText("已复制这条字幕")
        self.copy_feedback_timer.start()

    def _change_font(self, delta: int) -> None:
        font = self.list.font()
        font.setPointSize(max(9, min(24, font.pointSize() + delta)))
        self.list.setFont(font)
        self._reflow_items()

    def _reflow_items(self) -> None:
        for index in range(self.list.count()):
            self._reflow_item(self.list.item(index))

    def _reflow_item(self, item: QListWidgetItem) -> None:
        width = max(100, self.list.viewport().width() - 24)
        flags = Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere
        bounds = self.list.fontMetrics().boundingRect(
            QRect(0, 0, width, 10000), flags, item.text()
        )
        item.setSizeHint(QSize(width, bounds.height() + 22))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._reflow_items)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ) and hasattr(self, "list"):
            self._apply_palette()
