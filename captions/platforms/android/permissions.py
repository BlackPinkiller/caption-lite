from __future__ import annotations

from PySide6.QtCore import QMicrophonePermission, QObject, QPermission, Qt, Signal


class MicrophonePermissionBroker(QObject):
    granted = Signal()
    denied = Signal()

    def __init__(self, application, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._application = application

    def request(self) -> None:
        permission = QMicrophonePermission()
        status = self._application.checkPermission(permission)
        if status == Qt.PermissionStatus.Granted:
            self.granted.emit()
        elif status == Qt.PermissionStatus.Denied:
            self.denied.emit()
        else:
            self._application.requestPermission(
                permission,
                self,
                self._resolved,
            )

    def _resolved(self, permission: QPermission) -> None:
        if permission.status() == Qt.PermissionStatus.Granted:
            self.granted.emit()
        else:
            self.denied.emit()
