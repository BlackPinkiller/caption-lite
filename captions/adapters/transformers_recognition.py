from __future__ import annotations

import os
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np

from captions.config import AppConfig
from captions.high_precision_runtime import (
    high_precision_model_dir,
    high_precision_runtime_ready,
    high_precision_site_packages,
)
from captions.platforms.portable_paths import DEFAULT_APP_PATHS
from captions.ports.app_paths import AppPaths
from captions.ports.recognition import ASR_SAMPLE_RATE, RecognitionUpdate


_END = object()
_DLL_DIRECTORY_HANDLES: list[object] = []
_DLL_DIRECTORIES: set[str] = set()


def _activate_external_runtime(site_packages: Path) -> None:
    site_packages = site_packages.resolve()
    runtime_root = site_packages.parents[2]
    python_root = runtime_root / "python"
    base = next(
        (
            path
            for path in sorted(python_root.glob("cpython-*-windows-x86_64-none"))
            if (path / "Lib").is_dir() and (path / "DLLs").is_dir()
        ),
        None,
    )
    if base is None:
        raise RuntimeError("高精度识别组件的独立 Python 环境不完整")

    import_paths = (site_packages, base / "Lib", base / "DLLs")
    for path in reversed(import_paths):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    if hasattr(os, "add_dll_directory"):
        for path in (
            base,
            base / "DLLs",
            site_packages / "torch" / "lib",
            site_packages / "numpy.libs",
        ):
            value = str(path)
            if path.is_dir() and value not in _DLL_DIRECTORIES:
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(value))
                _DLL_DIRECTORIES.add(value)


class TransformersStreamingRecognition:
    def __init__(self, model_dir: Path, site_packages: Path, latency_ms: int) -> None:
        _activate_external_runtime(site_packages)
        try:
            import torch
            from transformers import (
                AutoModelForRNNT,
                AutoProcessor,
                TextIteratorStreamer,
            )
        except (ImportError, OSError) as error:
            detail = str(error).strip() or type(error).__name__
            raise RuntimeError(f"高精度识别组件无法加载：{detail}") from error
        if not torch.cuda.is_available():
            raise RuntimeError("高精度模式需要可用的 NVIDIA 显卡")

        lookahead = 6 if latency_ms == 560 else 13
        self._torch = torch
        self._streamer_type = TextIteratorStreamer
        self.processor = AutoProcessor.from_pretrained(
            model_dir,
            local_files_only=True,
        )
        self.processor.set_num_lookahead_tokens(lookahead)
        self.model = AutoModelForRNNT.from_pretrained(
            model_dir,
            dtype=torch.float32,
            local_files_only=True,
        ).to("cuda")
        self.model.eval()
        self._text_lock = threading.Lock()
        self._reset_state()

    def _reset_state(self) -> None:
        self._audio = np.empty(0, dtype=np.float32)
        self._next_start = 0
        self._started = False
        self._text = ""
        self._features: queue.Queue = queue.Queue()
        self._first_done = threading.Event()
        self._errors: list[BaseException] = []
        self._generate_thread: threading.Thread | None = None
        self._consume_thread: threading.Thread | None = None

    def reset(self) -> None:
        self._finish_stream()
        self._reset_state()

    def accept(self, samples: np.ndarray) -> RecognitionUpdate:
        self._raise_thread_error()
        self._audio = np.concatenate(
            (self._audio, np.asarray(samples, dtype=np.float32))
        )
        if not self._started:
            required = self.processor.num_samples_first_audio_chunk
            if self._audio.size < required:
                return RecognitionUpdate(self.text, False)
            first = self.processor(
                self._audio[:required],
                sampling_rate=ASR_SAMPLE_RATE,
                is_streaming=True,
                is_first_audio_chunk=True,
                return_tensors="pt",
            ).to(self.model.device, dtype=self.model.dtype)
            first_feature = first.input_features[
                :, : self.processor.num_mel_frames_first_audio_chunk, :
            ]
            self._next_start = (
                self.processor.num_mel_frames_first_audio_chunk
                * self.processor.feature_extractor.hop_length
                - self.processor.feature_extractor.n_fft // 2
            )
            self._start_stream(first, first_feature)
        self._enqueue_ready_chunks()
        self._wait_for_processing()
        return RecognitionUpdate(self.text, False)

    @property
    def text(self) -> str:
        with self._text_lock:
            return self._text.strip()

    def finalize(self) -> RecognitionUpdate:
        self.accept(np.zeros(ASR_SAMPLE_RATE * 2, dtype=np.float32))
        self._finish_stream()
        return RecognitionUpdate(self.text, False)

    def _start_stream(self, first, first_feature) -> None:
        self._started = True
        streamer = self._streamer_type(
            self.processor.tokenizer,
            skip_special_tokens=True,
        )

        def feature_generator():
            yield first_feature
            self._first_done.set()
            while True:
                item = self._features.get()
                try:
                    if item is _END:
                        return
                    yield item
                finally:
                    self._features.task_done()

        kwargs = {**first, "input_features": feature_generator(), "streamer": streamer}

        def generate() -> None:
            try:
                with self._torch.inference_mode():
                    self.model.generate(**kwargs)
            except BaseException as error:
                self._errors.append(error)
                streamer.end()

        def consume() -> None:
            try:
                for chunk in streamer:
                    with self._text_lock:
                        self._text += chunk
            except BaseException as error:
                self._errors.append(error)

        self._generate_thread = threading.Thread(target=generate, daemon=True)
        self._consume_thread = threading.Thread(target=consume, daemon=True)
        self._consume_thread.start()
        self._generate_thread.start()

    def _enqueue_ready_chunks(self) -> None:
        while (
            self._next_start + self.processor.num_samples_per_audio_chunk
            <= self._audio.size
        ):
            end = self._next_start + self.processor.num_samples_per_audio_chunk
            inputs = self.processor(
                self._audio[self._next_start:end],
                sampling_rate=ASR_SAMPLE_RATE,
                is_streaming=True,
                is_first_audio_chunk=False,
                return_tensors="pt",
            ).to(self.model.device, dtype=self.model.dtype)
            self._features.put(inputs.input_features)
            self._next_start += (
                self.processor.num_mel_frames_per_audio_chunk
                * self.processor.feature_extractor.hop_length
            )

    def _wait_for_processing(self) -> None:
        if not self._started:
            return
        if not self._first_done.wait(10):
            self._raise_thread_error()
            raise TimeoutError("高精度识别启动超时")
        deadline = time.monotonic() + 10
        while self._features.unfinished_tasks and time.monotonic() < deadline:
            self._raise_thread_error()
            time.sleep(0.005)
        if self._features.unfinished_tasks:
            raise TimeoutError("高精度识别处理超时")
        self._raise_thread_error()

    def _finish_stream(self) -> None:
        if not self._started or self._generate_thread is None:
            return
        if self._generate_thread.is_alive():
            self._features.put(_END)
            deadline = time.monotonic() + 10
            while self._features.unfinished_tasks and time.monotonic() < deadline:
                self._raise_thread_error()
                time.sleep(0.005)
        self._generate_thread.join(10)
        if self._consume_thread is not None:
            self._consume_thread.join(10)
        if self._generate_thread.is_alive():
            raise TimeoutError("高精度识别停止超时")
        self._raise_thread_error()

    def _raise_thread_error(self) -> None:
        if self._errors:
            error = self._errors[0]
            raise RuntimeError(f"高精度识别失败：{error}") from error


class TransformersRecognitionBackend:
    def __init__(self, *, app_paths: AppPaths = DEFAULT_APP_PATHS) -> None:
        self.app_paths = app_paths

    def create_streaming(self, config: AppConfig) -> TransformersStreamingRecognition:
        if not high_precision_runtime_ready(app_paths=self.app_paths):
            raise RuntimeError("高精度识别组件未安装")
        latency_ms = 560 if config.asr.model_variant == "english" else 1120
        return TransformersStreamingRecognition(
            high_precision_model_dir(app_paths=self.app_paths),
            high_precision_site_packages(app_paths=self.app_paths),
            latency_ms,
        )
