from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt


@dataclass
class SessionItem:
    cue_id: int
    source: str
    translation: str
    current: bool = False


class SessionListModel(QAbstractListModel):
    CueIdRole = Qt.ItemDataRole.UserRole + 1
    SourceRole = CueIdRole + 1
    TranslationRole = SourceRole + 1
    CurrentRole = TranslationRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[SessionItem] = []

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.CueIdRole: QByteArray(b"cueId"),
            self.SourceRole: QByteArray(b"source"),
            self.TranslationRole: QByteArray(b"translation"),
            self.CurrentRole: QByteArray(b"current"),
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        return {
            self.CueIdRole: item.cue_id,
            self.SourceRole: item.source,
            self.TranslationRole: item.translation,
            self.CurrentRole: item.current,
        }.get(role)

    def set_current(self, cue_id: int, source: str, translation: str = "") -> None:
        source = source.strip()
        translation = translation.strip()
        if self._items and self._items[-1].current:
            row = len(self._items) - 1
            item = self._items[row]
            item.cue_id = cue_id
            item.source = source
            item.translation = translation
            changed = self.index(row, 0)
            self.dataChanged.emit(
                changed,
                changed,
                [self.CueIdRole, self.SourceRole, self.TranslationRole],
            )
            return
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(SessionItem(cue_id, source, translation, True))
        self.endInsertRows()

    def commit_current(self) -> None:
        if not self._items or not self._items[-1].current:
            return
        row = len(self._items) - 1
        self._items[row].current = False
        changed = self.index(row, 0)
        self.dataChanged.emit(changed, changed, [self.CurrentRole])

    def set_translation(self, cue_id: int, translation: str) -> bool:
        for row in range(len(self._items) - 1, -1, -1):
            if self._items[row].cue_id != cue_id:
                continue
            self._items[row].translation = translation.strip()
            changed = self.index(row, 0)
            self.dataChanged.emit(changed, changed, [self.TranslationRole])
            return True
        return False

    def clear(self) -> None:
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()
