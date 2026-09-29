from __future__ import annotations

from captions.adapters.sherpa_onnx_recognition import SherpaOnnxRecognitionBackend
from captions.adapters.transformers_recognition import TransformersRecognitionBackend
from captions.core.settings import AppConfig
from captions.platforms.portable_paths import DEFAULT_APP_PATHS
from captions.ports.app_paths import AppPaths


class RecognitionRouter:
    def __init__(self, *, app_paths: AppPaths = DEFAULT_APP_PATHS) -> None:
        self.sherpa = SherpaOnnxRecognitionBackend(app_paths=app_paths)
        self.transformers = TransformersRecognitionBackend(app_paths=app_paths)

    def create_streaming(self, config: AppConfig):
        if config.asr.precision == "fp32":
            return self.transformers.create_streaming(config)
        return self.sherpa.create_streaming(config)

    def create_vad(self, config: AppConfig):
        return self.sherpa.create_vad(config)


DEFAULT_RECOGNITION_BACKEND = RecognitionRouter()
