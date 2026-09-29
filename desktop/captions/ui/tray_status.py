"""Compact hover text with the active download ahead of secondary details."""
from __future__ import annotations


def _compact(text: str, units: int) -> str:
    text = ' '.join(text.split())
    encoded = text.encode('utf-16-le')
    if len(encoded) <= units * 2:
        return text
    return encoded[:(units - 1) * 2].decode('utf-16-le', errors='ignore') + '…'


def tray_tooltip(status: str, device: str, model: str, download: str = '') -> str:
    # Budget in UTF-16 units, including emoji in device names, so the native
    # tray does not truncate the operation the user is trying to follow.
    title = '实时字幕'
    if download:
        title += ' · ' + _compact(download, 52)
    lines = [title, '状态：' + _compact(status, 24), '设备：' + _compact(device, 28)]
    if not download:
        lines.append('模型：' + _compact(model, 40))
    return '\n'.join(lines)
