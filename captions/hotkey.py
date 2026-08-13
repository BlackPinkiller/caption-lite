"""Backward-compatible import for the Windows native shortcut filter."""

from captions.platforms.windows.global_shortcut import (
    HOTKEY_ID,
    WM_HOTKEY,
    WindowsGlobalShortcut,
)


HotkeyFilter = WindowsGlobalShortcut
