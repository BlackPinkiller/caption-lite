from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from captions.core.settings import AppConfig, AsrConfig


MODEL_NAME = "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25"


ENGLISH_1120_MODEL_NAME = (
    "sherpa-onnx-nemotron-speech-streaming-en-0.6b-1120ms-int8-2026-04-25"
)


MULTILINGUAL_MODEL_NAME = (
    "sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-560ms-int8-2026-06-11"
)


MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{MODEL_NAME}.tar.bz2"
)


ENGLISH_1120_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{ENGLISH_1120_MODEL_NAME}.tar.bz2"
)


MULTILINGUAL_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{MULTILINGUAL_MODEL_NAME}.tar.bz2"
)


CHINESE_MODEL_NAME = "sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30"


CHINESE_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{CHINESE_MODEL_NAME}.tar.bz2"
)


NEMOTRON_MULTILINGUAL_LANGUAGES = (
    "en",
    "es",
    "fr",
    "it",
    "pt",
    "nl",
    "de",
    "tr",
    "ru",
    "ar",
    "hi",
    "ja",
    "ko",
    "vi",
    "uk",
    "pl",
    "sv",
    "cs",
    "nb",
    "da",
    "bg",
    "fi",
    "hr",
    "sk",
    "zh",
    "hu",
    "ro",
    "et",
)


@dataclass(frozen=True)
class ModelPreset:
    label: str
    name: str
    url: str
    size: int
    sha256: str
    encoder: str
    decoder: str
    joiner: str
    tokens: str = "tokens.txt"
    model_type: str = ""
    supported_languages: tuple[str, ...] = ()
    supports_auto_language: bool = False
    default_language: str = "auto"
    asr_max_utterance_seconds: float = 20.0

    @property
    def accepts_language_option(self) -> bool:
        return self.supports_auto_language or len(self.supported_languages) > 1


MODEL_CATALOG = {
    "english": ModelPreset(
        "Nemotron 560 ms（英文，默认）",
        MODEL_NAME,
        MODEL_URL,
        463_945_051,
        "78e2b79fcf7271553a74402a76b771b09ea40117a39566a79f52235b23db6358",
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "joiner.int8.onnx",
        supported_languages=("en",),
        default_language="en",
        asr_max_utterance_seconds=60.0,
    ),
    "english_1120": ModelPreset(
        "Nemotron 1120 ms（英文）",
        ENGLISH_1120_MODEL_NAME,
        ENGLISH_1120_MODEL_URL,
        463_945_058,
        "840c48deed02d4a5975716e7b12dc0a8b1ba620776c6366f7e5677d8907edd73",
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "joiner.int8.onnx",
        supported_languages=("en",),
        default_language="en",
        asr_max_utterance_seconds=60.0,
    ),
    "multilingual": ModelPreset(
        "Nemotron 3.5 560 ms（多语言）",
        MULTILINGUAL_MODEL_NAME,
        MULTILINGUAL_MODEL_URL,
        475_271_763,
        "c6bf5e0df765f9d5b43bc9e0536d4b4b3e7d40bdf5ecf13e45f134c51c05ae3a",
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "joiner.int8.onnx",
        supported_languages=NEMOTRON_MULTILINGUAL_LANGUAGES,
        supports_auto_language=True,
        default_language="auto",
    ),
    "chinese": ModelPreset(
        "Zipformer INT8（中文，轻量）",
        CHINESE_MODEL_NAME,
        CHINESE_MODEL_URL,
        132_634_597,
        "5a2832047ea1f97dd0dc595b816c230c4bafad65cfc0341fa57517cadc50afd0",
        "encoder.int8.onnx",
        "decoder.onnx",
        "joiner.int8.onnx",
        model_type="zipformer2",
        supported_languages=("zh",),
        default_language="zh",
    ),
}


MODEL_PRESETS = {
    key: (preset.name, preset.url) for key, preset in MODEL_CATALOG.items()
}


MODEL_DOWNLOAD_INTEGRITY = {
    key: (preset.size, preset.sha256) for key, preset in MODEL_CATALOG.items()
}


def model_download_spec(config: AppConfig) -> tuple[str, str]:
    return MODEL_PRESETS.get(config.asr.model_variant, MODEL_PRESETS["english"])


def model_download_integrity(config: AppConfig) -> tuple[int, str]:
    return MODEL_DOWNLOAD_INTEGRITY.get(
        config.asr.model_variant, MODEL_DOWNLOAD_INTEGRITY["english"]
    )


def model_preset(model_variant: str) -> ModelPreset:
    return MODEL_CATALOG.get(model_variant, MODEL_CATALOG["english"])


def supports_high_precision(model_variant: str) -> bool:
    return model_variant in {"english", "english_1120"}


def apply_model_preset(asr: AsrConfig, model_variant: str) -> None:
    preset = model_preset(model_variant)
    asr.model_variant = model_variant if model_variant in MODEL_CATALOG else "english"
    asr.model_dir = f"models/{preset.name}"
    asr.encoder = preset.encoder
    asr.decoder = preset.decoder
    asr.joiner = preset.joiner
    asr.tokens = preset.tokens
    asr.language = preset.default_language
    if not supports_high_precision(asr.model_variant):
        asr.precision = "int8"


def default_model_dir(model_variant: str) -> str:
    return f"models/{model_preset(model_variant).name}"
