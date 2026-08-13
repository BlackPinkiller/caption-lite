from __future__ import annotations

import sys

from captions.platforms.runtime import is_android_runtime
from captions.ports.audio_source import AudioCaptureKind, AudioSource


class UnsupportedAudioSource:
    capture_kind = AudioCaptureKind.SYSTEM_OUTPUT

    def open_default(self, **kwargs):
        raise RuntimeError("此平台尚未配置系统播放音频采集")


def create_audio_source() -> AudioSource:
    if is_android_runtime():
        from captions.platforms.android.audio_source import AndroidMicrophoneAudioSource

        return AndroidMicrophoneAudioSource()
    if sys.platform == "win32":
        from captions.platforms.windows.audio_source import WindowsSoundCardAudioSource

        return WindowsSoundCardAudioSource()
    return UnsupportedAudioSource()


DEFAULT_AUDIO_SOURCE = create_audio_source()
