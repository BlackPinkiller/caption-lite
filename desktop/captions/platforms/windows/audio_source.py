from __future__ import annotations

import warnings
from types import TracebackType

import numpy as np
import soundcard as sc

from captions.ports.audio_source import AudioCaptureKind


def _record_soundcard_samples(recorder, num_frames: int) -> np.ndarray:
    # SoundCard keeps the stream running after a WASAPI discontinuity, but it
    # repeats the same warning for every flagged packet. Keep all other audio
    # warnings visible while quieting only this known recoverable condition.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"^data discontinuity in recording$",
            category=sc.SoundcardRuntimeWarning,
        )
        return recorder.record(numframes=num_frames)


class SoundCardLoopbackCapture:
    def __init__(
        self,
        speaker,
        loopback,
        *,
        sample_rate: int,
        channels: int,
        block_size: int,
    ) -> None:
        self._speaker = speaker
        self._loopback = loopback
        self._sample_rate = sample_rate
        self._channels = channels
        self._block_size = block_size
        self._context = None
        self._recorder = None

    @property
    def name(self) -> str:
        return str(self._speaker.name)

    def __enter__(self) -> "SoundCardLoopbackCapture":
        self._context = self._loopback.recorder(
            samplerate=self._sample_rate,
            channels=self._channels,
            blocksize=self._block_size,
        )
        self._recorder = self._context.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._context is not None:
            self._context.__exit__(exc_type, exc_value, traceback)
        self._recorder = None
        self._context = None

    def read(self, num_frames: int) -> np.ndarray:
        if self._recorder is None:
            raise RuntimeError("音频采集尚未启动")
        return _record_soundcard_samples(self._recorder, num_frames)


class WindowsSoundCardAudioSource:
    capture_kind = AudioCaptureKind.SYSTEM_OUTPUT

    def open_default(
        self,
        *,
        sample_rate: int,
        channels: int,
        block_size: int,
    ) -> SoundCardLoopbackCapture:
        speaker = sc.default_speaker()
        if speaker is None:
            raise RuntimeError("没有找到默认播放设备")
        loopback = sc.get_microphone(speaker.id, include_loopback=True)
        return SoundCardLoopbackCapture(
            speaker,
            loopback,
            sample_rate=sample_rate,
            channels=channels,
            block_size=block_size,
        )
