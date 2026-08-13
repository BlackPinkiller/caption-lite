from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


WM_HOTKEY = 0x0312
HOTKEY_ID = 0xCA71


class WindowsGlobalShortcut(QObject, QAbstractNativeEventFilter):
    activated = Signal()

    def __init__(self, modifiers: int, virtual_key: int) -> None:
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self.modifiers = modifiers
        self.virtual_key = virtual_key
        self.registered = False
        self._application = None

    def install(self, application) -> bool:
        self.uninstall()
        self._application = application
        application.installNativeEventFilter(self)
        return self.register()

    def register(self) -> bool:
        self.unregister()
        self.registered = bool(
            ctypes.windll.user32.RegisterHotKey(
                None, HOTKEY_ID, self.modifiers, self.virtual_key
            )
        )
        return self.registered

    def uninstall(self) -> None:
        self.unregister()
        if self._application is not None:
            self._application.removeNativeEventFilter(self)
            self._application = None

    def unregister(self) -> None:
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        self.registered = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            self.activated.emit()
            return True, 0
        return False, 0
