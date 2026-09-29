from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from captions.core.model_catalog import MODEL_NAME
from captions.core.prompt_template import DEFAULT_LLM_PROMPT_TEMPLATE


@dataclass
class AsrConfig:
    model_variant: str = "english"
    precision: str = "int8"
    model_dir: str = f"models/{MODEL_NAME}"
    encoder: str = "encoder.int8.onnx"
    decoder: str = "decoder.int8.onnx"
    joiner: str = "joiner.int8.onnx"
    tokens: str = "tokens.txt"
    language: str = "en"
    auto_standby_seconds: int = 30
    num_threads: int = 2
    silence_endpoint_ms: int = 400
    silence_min_chars: int = 4


@dataclass
class LlmProviderConfig:
    id: str = "openai"
    name: str = "OpenAI"
    provider_type: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key: str = ""
    stream: bool = True


def default_llm_providers() -> list[LlmProviderConfig]:
    return [LlmProviderConfig()]


@dataclass
class TranslationConfig:
    enabled: bool = True
    backend: str = "llama"
    source_lang: str = "EN"
    target_lang: str = "ZH-HANS"
    llm_provider_id: str = "openai"
    llm_providers: list[LlmProviderConfig] = field(default_factory=default_llm_providers)
    google2_api_key: str = ""
    deepl_api_key: str = ""
    deepl_api_plan: str = "free"
    timeout_ms: int = 15000
    context_segments: int = 3
    context_chars: int = 1200
    prompt_template: str = DEFAULT_LLM_PROMPT_TEMPLATE
    glossary: dict[str, str] = field(default_factory=dict)


@dataclass
class SegmentationConfig:
    max_chars: int = 160
    split_lookback_chars: int = 32
    split_lookahead_chars: int = 160
    max_seconds: int = 20
    preview_min_chars: int = 4
    preview_interval_ms: int = 600
    preview_char_delta: int = 18
    punctuation_mode: str = "sentence"


@dataclass
class SubtitleConfig:
    theme: str = "clear"
    mode: str = "bilingual"
    max_sentences: int = 2
    font_family: str = "Microsoft YaHei UI"
    source_size: int = 18
    translation_size: int = 22
    text_color: str = "#ffffff"
    outline_color: str = "#000000"
    outline_width: float = 0.4
    shadow: bool = True
    line_spacing: int = 4
    align: str = "center"
    background: str = "none"
    background_color: str = "rgba(0,0,0,0.62)"
    background_radius: int = 6
    background_padding_y: int = 0
    padding: int = 12
    old_opacity: float = 0.7
    preview_opacity: float = 0.94
    custom_style: dict[str, Any] = field(default_factory=dict)
    stay_ms: int = 5000


@dataclass
class WindowConfig:
    width_percent: int = 70
    center_x_ratio: float = 0.5
    bottom_ratio: float = 0.1
    screen_name: str = ""
    x: int = 240
    y: int = 700
    width: int = 1200
    height: int = 220
    locked: bool = False


@dataclass
class HotkeyConfig:
    modifiers: int = 3
    virtual_key: int = 0x4C


@dataclass
class DebugConfig:
    enabled: bool = False
    include_text: bool = False


@dataclass
class AppConfig:
    asr: AsrConfig = field(default_factory=AsrConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)


def _compatible_value(default: Any, value: Any) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, dict):
        return isinstance(value, dict) and all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in value.items()
        )
    return isinstance(value, type(default))


def _merge_dataclass(instance: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if hasattr(instance, key) and _compatible_value(getattr(instance, key), value):
            setattr(instance, key, value)


def active_llm_provider(config: TranslationConfig) -> LlmProviderConfig:
    for provider in config.llm_providers:
        if provider.id == config.llm_provider_id:
            return provider
    return config.llm_providers[0] if config.llm_providers else LlmProviderConfig()


def translation_secret_values(config: TranslationConfig) -> tuple[str, ...]:
    return (
        config.google2_api_key, config.deepl_api_key,
        *(provider.api_key for provider in config.llm_providers),
    )


def llm_chat_completions_url(provider: LlmProviderConfig) -> str:
    base_url = provider.base_url.strip().rstrip("/")
    if base_url.lower().endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions" if base_url else ""


def _clamp(value: int | float, minimum: int | float, maximum: int | float):
    return max(minimum, min(maximum, value))


def clone_config(config: AppConfig) -> AppConfig:
    return copy.deepcopy(config)
