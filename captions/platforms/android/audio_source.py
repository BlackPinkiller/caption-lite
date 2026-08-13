from __future__ import annotations

import time
from types import TracebackType

import numpy as np
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices

from captions.ports.audio_source import AudioCaptureKind


PCM_SAMPLE_WIDTH = 2


def _pcm16le_to_float32(data: bytes, channels: int) -> np.ndarray:
    samples = np.frombuffer(data, dtype="<i2").astype(np.float32)
    samples *= 1.0 / 32768.0
    return samples.reshape((-1, channels))


class AndroidMicrophoneCapture:
    def __init__(
        self,
        device,
        audio_format: QAudioFormat,
        *,
        block_size: int,
    ) -> None:
        self._device = device
        self._format = audio_format
        self._channels = audio_format.channelCount()
        self._block_size = block_size
        self._source: QAudioSource | None = None
        self._stream = None
        self._pending = bytearray()

    @property
    def name(self) -> str:
        return self._device.description() or "麦克风"

    def __enter__(self) -> "AndroidMicrophoneCapture":
        source = QAudioSource(self._device, self._format)
        source.setBufferSize(
            self._block_size * self._channels * PCM_SAMPLE_WIDTH
        )
        stream = source.start()
        if stream is None:
            raise RuntimeError("无法启动麦克风")
        self._source = source
        self._stream = stream
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._source is not None:
            self._source.stop()
        self._stream = None
        self._source = None
        self._pending.clear()

    def read(self, num_frames: int) -> np.ndarray:
        if self._source is None or self._stream is None:
            raise RuntimeError("麦克风采集尚未启动")
        required = num_frames * self._channels * PCM_SAMPLE_WIDTH
        while len(self._pending) < required:
            available = int(self._stream.bytesAvailable())
            if available > 0:
                chunk = bytes(self._stream.read(available))
                if chunk:
                    self._pending.extend(chunk)
                    continue
            if (
                self._source.state() == QAudio.State.StoppedState
                and self._source.error() != QAudio.Error.NoError
            ):
                raise RuntimeError(f"麦克风采集已停止：{self._source.error().name}")
            time.sleep(0.01)
        data = bytes(self._pending[:required])
        del self._pending[:required]
        return _pcm16le_to_float32(data, self._channels)


class AndroidMicrophoneAudioSource:
    capture_kind = AudioCaptureKind.MICROPHONE

    def open_default(
        self,
        *,
        sample_rate: int,
        channels: int,
        block_size: int,
    ) -> AndroidMicrophoneCapture:
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            raise RuntimeError("没有找到麦克风")
        audio_format = QAudioFormat()
        audio_format.setSampleRate(sample_rate)
        audio_format.setChannelCount(channels)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(audio_format):
            raise RuntimeError("麦克风不支持 16 kHz 单声道采集")
        return AndroidMicrophoneCapture(
            device,
            audio_format,
            block_size=block_size,
        )
