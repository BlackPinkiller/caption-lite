from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal

from captions.ports.global_shortcut import GlobalShortcut


class DisabledGlobalShortcut(QObject):
    activated = Signal()

    def install(self, application) -> bool:
        return False

    def uninstall(self) -> None:
        return None


def create_global_shortcut(modifiers: int, virtual_key: int) -> GlobalShortcut:
    if sys.platform == "win32":
        from captions.platforms.windows.global_shortcut import WindowsGlobalShortcut

        return WindowsGlobalShortcut(modifiers, virtual_key)
    return DisabledGlobalShortcut()
