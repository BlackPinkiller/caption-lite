from __future__ import annotations

import numpy as np

from captions.config import AppConfig, model_preset, resolve_model_files
from captions.platforms.portable_paths import DEFAULT_APP_PATHS
from captions.ports.app_paths import AppPaths
from captions.ports.recognition import ASR_SAMPLE_RATE, VAD_WINDOW_SIZE, RecognitionUpdate


class SherpaStreamingRecognition:
    def __init__(self, recognizer, stream) -> None:
        self._recognizer = recognizer
        self._stream = stream

    def reset(self) -> None:
        self._recognizer.reset(self._stream)

    def accept(self, samples: np.ndarray) -> RecognitionUpdate:
        self._stream.accept_waveform(ASR_SAMPLE_RATE, samples)
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)
        return RecognitionUpdate(
            text=str(self._recognizer.get_result(self._stream)).strip(),
            endpoint=bool(self._recognizer.is_endpoint(self._stream)),
        )

    def finalize(self) -> RecognitionUpdate:
        return self.accept(np.zeros(9600, dtype=np.float32))


class SherpaOnnxRecognitionBackend:
    def __init__(self, *, app_paths: AppPaths = DEFAULT_APP_PATHS) -> None:
        self.app_paths = app_paths

    @staticmethod
    def _sherpa():
        try:
            import sherpa_onnx
        except ImportError as error:
            raise RuntimeError(
                "缺少 sherpa-onnx，请先运行 tools\\setup.ps1"
            ) from error
        return sherpa_onnx

    def create_streaming(self, config: AppConfig) -> SherpaStreamingRecognition:
        sherpa_onnx = self._sherpa()
        files = resolve_model_files(config, app_paths=self.app_paths)
        missing = [str(path) for path in files.values() if not path.is_file()]
        if missing:
            raise RuntimeError(
                "语音识别模型不完整，请将模型文件放入以下位置：\n"
                + "\n".join(missing)
            )
        recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(files["tokens"]),
            encoder=str(files["encoder"]),
            decoder=str(files["decoder"]),
            joiner=str(files["joiner"]),
            num_threads=config.asr.num_threads,
            sample_rate=ASR_SAMPLE_RATE,
            feature_dim=80,
            provider="cpu",
            decoding_method="greedy_search",
            model_type=model_preset(config.asr.model_variant).model_type,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=2.4,
            rule3_min_utterance_length=20.0,
        )
        stream = recognizer.create_stream()
        if model_preset(config.asr.model_variant).accepts_language_option:
            stream.set_option("language", config.asr.language or "auto")
        return SherpaStreamingRecognition(recognizer, stream)

    def create_vad(self, config: AppConfig):
        sherpa_onnx = self._sherpa()
        model = self.app_paths.bundled_resource("silero_vad.int8.onnx")
        if not model.is_file():
            raise RuntimeError(f"缺少 Silero VAD 模型：{model}")
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(model)
        vad_config.silero_vad.threshold = 0.25
        vad_config.silero_vad.min_silence_duration = (
            config.asr.silence_endpoint_ms / 1000
        )
        vad_config.silero_vad.min_speech_duration = 0.25
        vad_config.silero_vad.max_speech_duration = 20.0
        vad_config.silero_vad.window_size = VAD_WINDOW_SIZE
        vad_config.sample_rate = ASR_SAMPLE_RATE
        vad_config.num_threads = 1
        return sherpa_onnx.VoiceActivityDetector(
            vad_config, buffer_size_in_seconds=30
        )


DEFAULT_RECOGNITION_BACKEND = SherpaOnnxRecognitionBackend()
