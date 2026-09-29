"""Connection-test feedback belongs to the settings revision that requested it."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QLabel, QPushButton


class TranslationTestFeedback(QObject):
    def __init__(
        self, label: QLabel, button: QPushButton, enabled: Callable[[], bool], parent=None,
    ) -> None:
        super().__init__(parent)
        self.label = label
        self.button = button
        self.enabled = enabled
        self._revision = 0

    def clear(self, *args) -> None:
        self._revision += 1
        self.show_status("")

    def begin(self) -> int:
        self._revision += 1
        self.show_status("正在测试连接…")
        return self._revision

    def finish(self, revision: int, text: str, *, success: bool) -> None:
        if revision == self._revision:
            self.show_status(text, success=success)

    def show_status(self, text: str, *, success: bool | None = None) -> None:
        self.label.setText(text)
        self.label.setVisible(bool(text))
        color = "#2e7d32" if success is True else "#b3261e" if success is False else "#777"
        self.label.setStyleSheet(f"color:{color}")
        self.button.setEnabled(self.enabled() and (not text or success is not None))
