from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from captions.adapters.recognition_router import DEFAULT_RECOGNITION_BACKEND
from captions.config import AppConfig
from captions.core.diagnostics import Diagnostics, NULL_DIAGNOSTICS
from captions.platforms.audio_source import DEFAULT_AUDIO_SOURCE
from captions.ports.audio_source import AudioCaptureKind, AudioSource
from captions.ports.recognition import ASR_SAMPLE_RATE, VAD_WINDOW_SIZE, RecognitionBackend
from captions.segmenter import should_commit_endpoint


AUDIO_ACTIVITY_THRESHOLD = 0.0001
VAD_PRE_ROLL_WINDOWS = 48
NEMOTRON_560_VAD_PRE_ROLL_WINDOWS = 32
VAD_FLUSH_SAMPLES = 9600
CAPTURE_BLOCK_SIZE = VAD_WINDOW_SIZE * 3
CAPTURE_BUFFER_SIZE = 8960


def vad_pre_roll_windows(model_variant: str) -> int:
    if model_variant == "english":
        return NEMOTRON_560_VAD_PRE_ROLL_WINDOWS
    return VAD_PRE_ROLL_WINDOWS


def capture_status_text(capture_kind: AudioCaptureKind, state: str) -> str:
    if capture_kind == AudioCaptureKind.MICROPHONE:
        return {
            "connecting": "正在连接麦克风…",
            "reconnecting": "麦克风已变化，正在重连",
        }[state]
    return {
        "connecting": "正在连接系统播放设备…",
        "reconnecting": "播放设备已变化，正在重连",
    }[state]


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
    """Gates non-speech audio while preserving the sentence onset.

    Only windows around confirmed speech are forwarded to the recognizer
    (saving CPU on silence), but the pre-roll is large enough to cover the
    VAD confirmation latency so the first words of the next sentence are
    never evicted. The pre-roll only accumulates while speech is inactive and
    is cleared after each detection, so it never re-feeds the previous
    sentence's tail.
    """

    def __init__(
        self,
        vad,
        window_size: int = VAD_WINDOW_SIZE,
        pre_roll_windows: int = VAD_PRE_ROLL_WINDOWS,
    ) -> None:
        self.vad = vad
        self.window_size = window_size
        self.pending = np.empty(0, dtype=np.float32)
        self.pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_windows)
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

    def __init__(
        self,
        config: AppConfig,
        *,
        audio_source: AudioSource = DEFAULT_AUDIO_SOURCE,
        recognition_backend: RecognitionBackend = DEFAULT_RECOGNITION_BACKEND,
        diagnostics: Diagnostics = NULL_DIAGNOSTICS,
    ) -> None:
        super().__init__()
        self.config = config
        self.audio_source = audio_source
        self.recognition_backend = recognition_backend
        self.diagnostics = diagnostics
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._standby = AutoStandbyDetector(config.asr.auto_standby_seconds)
        self._silence_min_chars = config.asr.silence_min_chars

    @Slot()
    def run(self) -> None:
        try:
            recognition = self.recognition_backend.create_streaming(self.config)
            speech_gate = VadSpeechGate(
                self.recognition_backend.create_vad(self.config),
                pre_roll_windows=vad_pre_roll_windows(
                    self.config.asr.model_variant
                ),
            )
            if self._stop.is_set():
                return
            self.model_ready.emit()
            self.diagnostics.event("asr.ready")
            revision = 0
            last_text = ""
            while not self._stop.is_set():
                if self._pause.is_set():
                    recognition.reset()
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
                self.status.emit(
                    capture_status_text(
                        self.audio_source.capture_kind,
                        "connecting",
                    )
                )
                capture = self.audio_source.open_default(
                    sample_rate=ASR_SAMPLE_RATE,
                    channels=1,
                    block_size=CAPTURE_BUFFER_SIZE,
                )
                self.diagnostics.event("capture.connected", device=capture.name)
                self.status.emit(f"正在识别：{capture.name}")
                try:
                    with capture:
                        while not self._stop.is_set():
                            if self._pause.is_set():
                                break
                            samples = capture.read(CAPTURE_BLOCK_SIZE)
                            mono = np.asarray(samples[:, 0], dtype=np.float32)
                            level = float(np.max(np.abs(mono))) if mono.size else 0.0
                            standby_change = self._standby.update(level)
                            if standby_change is True:
                                self.diagnostics.event("capture.standby_entered")
                                recognition.reset()
                                speech_gate.reset()
                                last_text = ""
                                self.auto_standby_changed.emit(True)
                                self.status.emit("自动待机")
                                continue
                            if standby_change is False:
                                self.diagnostics.event("capture.standby_left")
                                speech_gate.reset()
                                self.auto_standby_changed.emit(False)
                                self.status.emit(f"正在识别：{capture.name}")
                            elif self._standby.standby:
                                continue
                            for speech, vad_endpoint in speech_gate.process(mono):
                                update = recognition.accept(speech)
                                text = update.text
                                if vad_endpoint and text.strip():
                                    finalize = getattr(recognition, "finalize", None)
                                    flush = (
                                        finalize()
                                        if callable(finalize)
                                        else recognition.accept(
                                            np.zeros(
                                                VAD_FLUSH_SAMPLES,
                                                dtype=np.float32,
                                            )
                                        )
                                    )
                                    if flush.text:
                                        text = flush.text
                                if text != last_text:
                                    revision += 1
                                    last_text = text
                                    self.diagnostics.event(
                                        "asr.partial",
                                        revision=revision,
                                        text=text,
                                    )
                                    self.partial.emit(text, revision)
                                commit_endpoint = should_commit_endpoint(
                                    text,
                                    vad_endpoint=vad_endpoint,
                                    asr_endpoint=update.endpoint,
                                    silence_min_chars=self._silence_min_chars,
                                )
                                if commit_endpoint:
                                    self.diagnostics.event(
                                        "asr.endpoint",
                                        revision=revision,
                                        reason="asr" if update.endpoint else "vad",
                                        text=text,
                                    )
                                    self.endpoint.emit()
                                    recognition.reset()
                                    last_text = ""
                                elif vad_endpoint and not text.strip():
                                    recognition.reset()
                                    last_text = ""
                except Exception as error:
                    if self._stop.is_set():
                        break
                    self.diagnostics.event(
                        "capture.reconnecting",
                        error=str(error),
                    )
                    recognition.reset()
                    speech_gate.reset()
                    last_text = ""
                    reconnecting = capture_status_text(
                        self.audio_source.capture_kind,
                        "reconnecting",
                    )
                    self.status.emit(f"{reconnecting}：{error}")
                    time.sleep(1)
        except Exception as error:
            self.diagnostics.event("asr.error", error=str(error))
            self.error.emit(str(error))
        finally:
            self.diagnostics.event("asr.stopped")
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

    def set_silence_min_chars(self, chars: int) -> None:
        self._silence_min_chars = max(1, int(chars))
        self.config.asr.silence_min_chars = self._silence_min_chars
