from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


WM_HOTKEY = 0x0312
HOTKEY_ID = 0xCA71


class HotkeyFilter(QObject, QAbstractNativeEventFilter):
    activated = Signal()

    def __init__(self, modifiers: int, virtual_key: int) -> None:
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self.modifiers = modifiers
        self.virtual_key = virtual_key
        self.registered = False

    def register(self) -> bool:
        if sys.platform != "win32":
            return False
        self.unregister()
        self.registered = bool(
            ctypes.windll.user32.RegisterHotKey(
                None, HOTKEY_ID, self.modifiers, self.virtual_key
            )
        )
        return self.registered

    def unregister(self) -> None:
        if self.registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        self.registered = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if sys.platform == "win32":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.activated.emit()
                return True, 0
        return False, 0
