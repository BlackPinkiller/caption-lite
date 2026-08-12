from __future__ import annotations

import threading
import time
import warnings
from collections import deque

import numpy as np
import soundcard as sc
from PySide6.QtCore import QObject, Signal, Slot

from captions.config import (
    AppConfig,
    bundled_resource_path,
    model_preset,
    resolve_model_files,
)


AUDIO_ACTIVITY_THRESHOLD = 0.0001
VAD_WINDOW_SIZE = 512
VAD_PRE_ROLL_WINDOWS = 16
CAPTURE_BLOCK_SIZE = VAD_WINDOW_SIZE * 3
CAPTURE_BUFFER_SIZE = 8960


def _record_samples(recorder) -> np.ndarray:
    # SoundCard keeps the stream running after a WASAPI discontinuity, but it
    # repeats the same warning for every flagged packet. Keep all other audio
    # warnings visible while quieting only this known recoverable condition.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"^data discontinuity in recording$",
            category=sc.SoundcardRuntimeWarning,
        )
        return recorder.record(numframes=CAPTURE_BLOCK_SIZE)


class AutoStandbyDetector:
    def __init__(self, timeout_seconds: int, *, now: float | None = None) -> None:
        self.timeout_seconds = max(0, int(timeout_seconds))
        self.last_activity_at = time.monotonic() if now is None else now
        self.standby = False

    def configure(self, timeout_seconds: int, *, now: float | None = None) -> bool:
        self.timeout_seconds = max(0, int(timeout_seconds))
        self.last_activity_at = time.monotonic() if now is None else now
        was_standby = self.standby
        if not self.timeout_seconds:
            self.standby = False
        return was_standby and not self.standby

    def update(self, level: float, *, now: float | None = None) -> bool | None:
        now = time.monotonic() if now is None else now
        if level >= AUDIO_ACTIVITY_THRESHOLD:
            self.last_activity_at = now
            if self.standby:
                self.standby = False
                return False
            return None
        if (
            self.timeout_seconds
            and not self.standby
            and now - self.last_activity_at >= self.timeout_seconds
        ):
            self.standby = True
            return True
        return None


class VadSpeechGate:
    def __init__(self, vad, window_size: int = VAD_WINDOW_SIZE) -> None:
        self.vad = vad
        self.window_size = window_size
        self.pending = np.empty(0, dtype=np.float32)
        self.pre_roll: deque[np.ndarray] = deque(maxlen=VAD_PRE_ROLL_WINDOWS)
        self.speech_active = False

    def reset(self) -> None:
        self.vad.reset()
        self.pending = np.empty(0, dtype=np.float32)
        self.pre_roll.clear()
        self.speech_active = False

    def process(self, samples: np.ndarray) -> list[tuple[np.ndarray, bool]]:
        samples = np.asarray(samples, dtype=np.float32)
        if self.pending.size:
            samples = np.concatenate((self.pending, samples))
        events: list[tuple[np.ndarray, bool]] = []
        offset = 0
        while offset + self.window_size <= samples.size:
            window = samples[offset : offset + self.window_size]
            offset += self.window_size
            was_active = self.speech_active
            if not was_active:
                self.pre_roll.append(window.copy())
            self.vad.accept_waveform(window)
            detected = bool(self.vad.is_speech_detected())
            if was_active:
                events.append((window, not detected))
            elif detected:
                events.append((np.concatenate(tuple(self.pre_roll)), False))
                self.pre_roll.clear()
            self.speech_active = detected
            while not self.vad.empty():
                self.vad.pop()
        self.pending = samples[offset:].copy()
        return events


class AudioAsrWorker(QObject):
    partial = Signal(str, int)
    endpoint = Signal()
    status = Signal(str)
    model_ready = Signal()
    auto_standby_changed = Signal(bool)
    error = Signal(str)
    stopped = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._standby = AutoStandbyDetector(config.asr.auto_standby_seconds)

    @Slot()
    def run(self) -> None:
        try:
            recognizer = self._create_recognizer()
            speech_gate = VadSpeechGate(self._create_vad())
            if self._stop.is_set():
                return
            self.model_ready.emit()
            stream = self._create_stream(recognizer)
            revision = 0
            last_text = ""
            while not self._stop.is_set():
                if self._pause.is_set():
                    recognizer.reset(stream)
                    speech_gate.reset()
                    last_text = ""
                    if self._standby.standby:
                        self._standby.standby = False
                        self.auto_standby_changed.emit(False)
                    self.status.emit("识别已暂停")
                    while self._pause.is_set() and not self._stop.is_set():
                        time.sleep(0.1)
                    if self._stop.is_set():
                        break
                self.status.emit("正在连接系统播放设备…")
                speaker = sc.default_speaker()
                if speaker is None:
                    raise RuntimeError("没有找到默认播放设备")
                loopback = sc.get_microphone(speaker.id, include_loopback=True)
                self.status.emit(f"正在识别：{speaker.name}")
                try:
                    with loopback.recorder(
                        samplerate=16000,
                        channels=1,
                        blocksize=CAPTURE_BUFFER_SIZE,
                    ) as recorder:
                        while not self._stop.is_set():
                            if self._pause.is_set():
                                break
                            samples = _record_samples(recorder)
                            mono = np.asarray(samples[:, 0], dtype=np.float32)
                            level = float(np.max(np.abs(mono))) if mono.size else 0.0
                            standby_change = self._standby.update(level)
                            if standby_change is True:
                                recognizer.reset(stream)
                                speech_gate.reset()
                                last_text = ""
                                self.auto_standby_changed.emit(True)
                                self.status.emit("自动待机")
                                continue
                            if standby_change is False:
                                speech_gate.reset()
                                self.auto_standby_changed.emit(False)
                                self.status.emit(f"正在识别：{speaker.name}")
                            elif self._standby.standby:
                                continue
                            for speech, vad_endpoint in speech_gate.process(mono):
                                stream.accept_waveform(16000, speech)
                                while recognizer.is_ready(stream):
                                    recognizer.decode_stream(stream)
                                text = str(recognizer.get_result(stream)).strip()
                                if text != last_text:
                                    revision += 1
                                    last_text = text
                                    self.partial.emit(text, revision)
                                if vad_endpoint or recognizer.is_endpoint(stream):
                                    self.endpoint.emit()
                                    recognizer.reset(stream)
                                    last_text = ""
                except Exception as error:
                    if self._stop.is_set():
                        break
                    recognizer.reset(stream)
                    speech_gate.reset()
                    last_text = ""
                    self.status.emit(f"播放设备已变化，正在重连：{error}")
                    time.sleep(1)
        except Exception as error:
            self.error.emit(str(error))
        finally:
            self.stopped.emit()

    def stop(self) -> None:
        self._stop.set()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        woke = self._standby.configure(self.config.asr.auto_standby_seconds)
        if woke:
            self.auto_standby_changed.emit(False)
        self._pause.clear()

    def set_auto_standby_seconds(self, seconds: int) -> None:
        self.config.asr.auto_standby_seconds = max(0, int(seconds))
        woke = self._standby.configure(seconds)
        if woke:
            self.auto_standby_changed.emit(False)

    def _create_stream(self, recognizer):
        stream = recognizer.create_stream()
        if model_preset(self.config.asr.model_variant).accepts_language_option:
            stream.set_option("language", self.config.asr.language or "auto")
        return stream

    def _create_vad(self):
        try:
            import sherpa_onnx
        except ImportError as error:
            raise RuntimeError(
                "缺少 sherpa-onnx，请先运行 tools\\setup.ps1"
            ) from error
        model = bundled_resource_path("silero_vad.int8.onnx")
        if not model.is_file():
            raise RuntimeError(f"缺少 Silero VAD 模型：{model}")
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(model)
        config.silero_vad.threshold = 0.25
        config.silero_vad.min_silence_duration = (
            self.config.asr.silence_endpoint_ms / 1000
        )
        config.silero_vad.min_speech_duration = 0.25
        config.silero_vad.max_speech_duration = 20.0
        config.silero_vad.window_size = VAD_WINDOW_SIZE
        config.sample_rate = 16000
        config.num_threads = 1
        return sherpa_onnx.VoiceActivityDetector(
            config, buffer_size_in_seconds=30
        )

    def _create_recognizer(self, provider: str = "cpu"):
        try:
            import sherpa_onnx
        except ImportError as error:
            raise RuntimeError(
                "缺少 sherpa-onnx，请先运行 tools\\setup.ps1"
            ) from error
        files = resolve_model_files(self.config)
        missing = [str(path) for path in files.values() if not path.is_file()]
        if missing:
            raise RuntimeError(
                "语音识别模型不完整，请将模型文件放入以下位置：\n"
                + "\n".join(missing)
            )
        return sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(files["tokens"]),
            encoder=str(files["encoder"]),
            decoder=str(files["decoder"]),
            joiner=str(files["joiner"]),
            num_threads=self.config.asr.num_threads,
            sample_rate=16000,
            feature_dim=80,
            provider=provider,
            decoding_method="greedy_search",
            model_type=model_preset(self.config.asr.model_variant).model_type,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=2.4,
            rule3_min_utterance_length=20.0,
        )
