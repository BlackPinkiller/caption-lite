from __future__ import annotations

import copy
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from captions.core.prompt_template import (
    DEFAULT_LLM_PROMPT_TEMPLATE,
    normalize_prompt_template_placeholders,
    prompt_template_with_preference,
)
from captions.platforms.portable_paths import DEFAULT_APP_PATHS
from captions.platforms.secret_store import DEFAULT_SECRET_STORE
from captions.ports.app_paths import AppPaths
from captions.ports.secret_store import SecretStore, SecretStoreError


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


def application_dir() -> Path:
    return DEFAULT_APP_PATHS.application_dir()


def bundled_resource_path(name: str) -> Path:
    return DEFAULT_APP_PATHS.bundled_resource(name)


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
    split_punctuation: bool = True


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


@dataclass
class AppConfig:
    asr: AsrConfig = field(default_factory=AsrConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)


SUBTITLE_STYLE_FIELDS = (
    "font_family",
    "source_size",
    "translation_size",
    "text_color",
    "outline_color",
    "outline_width",
    "shadow",
    "line_spacing",
    "align",
    "background",
    "background_color",
    "background_radius",
    "background_padding_y",
    "padding",
    "old_opacity",
    "preview_opacity",
)

SUBTITLE_THEME_PRESETS: dict[str, dict[str, Any]] = {
    "clear": {
        "label": "清晰",
        "font_family": "Microsoft YaHei UI",
        "source_size": 18,
        "translation_size": 22,
        "text_color": "#ffffff",
        "outline_color": "#000000",
        "outline_width": 0.4,
        "shadow": True,
        "line_spacing": 4,
        "align": "center",
        "background": "none",
        "background_color": "rgba(0,0,0,0.62)",
        "background_radius": 6,
        "background_padding_y": 0,
        "padding": 12,
        "old_opacity": 0.7,
        "preview_opacity": 0.94,
    },
    "television": {
        "label": "电视字幕",
        "font_family": "Microsoft YaHei UI",
        "source_size": 15,
        "translation_size": 20,
        "text_color": "#ffd84d",
        "outline_color": "#000000",
        "outline_width": 0.0,
        "shadow": False,
        "line_spacing": 2,
        "align": "left",
        "background": "line",
        "background_color": "rgba(0,0,0,0.9)",
        "background_radius": 4,
        "background_padding_y": 2,
        "padding": 12,
        "old_opacity": 0.68,
        "preview_opacity": 0.86,
    },
    "soft": {
        "label": "柔和",
        "font_family": "Microsoft YaHei UI",
        "source_size": 17,
        "translation_size": 21,
        "text_color": "#e0f2fe",
        "outline_color": "#0f172a",
        "outline_width": 0.0,
        "shadow": False,
        "line_spacing": 8,
        "align": "center",
        "background": "block",
        "background_color": "rgba(15,23,42,0.82)",
        "background_radius": 18,
        "background_padding_y": 7,
        "padding": 18,
        "old_opacity": 0.58,
        "preview_opacity": 0.9,
    },
}


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


def _llm_provider_from_dict(values: Any) -> LlmProviderConfig | None:
    if not isinstance(values, dict):
        return None
    provider = LlmProviderConfig()
    _merge_dataclass(provider, values)
    return provider


def _legacy_llm_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    suffix = "/chat/completions"
    if url.lower().endswith(suffix):
        return url[: -len(suffix)]
    return url


def active_llm_provider(config: TranslationConfig) -> LlmProviderConfig:
    for provider in config.llm_providers:
        if provider.id == config.llm_provider_id:
            return provider
    return config.llm_providers[0] if config.llm_providers else LlmProviderConfig()


def llm_chat_completions_url(provider: LlmProviderConfig) -> str:
    base_url = provider.base_url.strip().rstrip("/")
    if base_url.lower().endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions" if base_url else ""


def _clamp(value: int | float, minimum: int | float, maximum: int | float):
    return max(minimum, min(maximum, value))


def subtitle_style_values(subtitle: SubtitleConfig) -> dict[str, Any]:
    return {
        name: copy.deepcopy(getattr(subtitle, name))
        for name in SUBTITLE_STYLE_FIELDS
    }


def _normalize_subtitle_appearance(subtitle: SubtitleConfig) -> None:
    defaults = SubtitleConfig()
    subtitle.source_size = int(_clamp(subtitle.source_size, 14, 72))
    subtitle.translation_size = int(_clamp(subtitle.translation_size, 14, 72))
    subtitle.outline_width = float(_clamp(subtitle.outline_width, 0, 1))
    subtitle.line_spacing = int(_clamp(subtitle.line_spacing, 0, 32))
    if subtitle.align not in {"left", "center", "right"}:
        subtitle.align = defaults.align
    if subtitle.background not in {"none", "line", "block"}:
        subtitle.background = defaults.background
    subtitle.background_radius = int(_clamp(subtitle.background_radius, 0, 24))
    subtitle.background_padding_y = int(
        _clamp(subtitle.background_padding_y, 0, 24)
    )
    subtitle.padding = int(_clamp(subtitle.padding, 0, 48))
    subtitle.old_opacity = float(_clamp(subtitle.old_opacity, 0, 1))
    subtitle.preview_opacity = float(_clamp(subtitle.preview_opacity, 0, 1))


def _normalized_subtitle_style(
    values: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    candidate = SubtitleConfig()
    for source in (fallback, values):
        for name in SUBTITLE_STYLE_FIELDS:
            value = source.get(name)
            if value is not None and _compatible_value(getattr(candidate, name), value):
                setattr(candidate, name, copy.deepcopy(value))
    _normalize_subtitle_appearance(candidate)
    return subtitle_style_values(candidate)


def subtitle_custom_style(subtitle: SubtitleConfig) -> dict[str, Any]:
    return _normalized_subtitle_style(
        subtitle.custom_style,
        subtitle_style_values(subtitle),
    )


def apply_subtitle_theme(subtitle: SubtitleConfig, theme: str) -> None:
    if theme == "custom":
        values = subtitle_custom_style(subtitle)
    else:
        preset = SUBTITLE_THEME_PRESETS.get(theme, SUBTITLE_THEME_PRESETS["clear"])
        values = preset
        theme = theme if theme in SUBTITLE_THEME_PRESETS else "clear"
    for name in SUBTITLE_STYLE_FIELDS:
        setattr(subtitle, name, copy.deepcopy(values[name]))
    subtitle.theme = theme


def _normalize_config(config: AppConfig) -> None:
    defaults = AppConfig()
    if config.asr.model_variant not in MODEL_PRESETS:
        config.asr.model_variant = defaults.asr.model_variant
    preset = MODEL_CATALOG[config.asr.model_variant]
    if (
        config.asr.precision not in {"int8", "fp32"}
        or not supports_high_precision(config.asr.model_variant)
    ):
        config.asr.precision = "int8"
    valid_languages = set(preset.supported_languages)
    if preset.supports_auto_language:
        valid_languages.add("auto")
    if config.asr.language not in valid_languages:
        config.asr.language = preset.default_language
    config.asr.auto_standby_seconds = int(
        _clamp(config.asr.auto_standby_seconds, 0, 3600)
    )
    if config.asr.num_threads not in {1, 2, 4, 8}:
        config.asr.num_threads = defaults.asr.num_threads
    config.asr.silence_endpoint_ms = int(
        _clamp(config.asr.silence_endpoint_ms, 300, 1500)
    )
    config.asr.silence_min_chars = int(
        _clamp(config.asr.silence_min_chars, 1, 100)
    )

    if config.translation.backend not in {"llama", "google2", "deepl"}:
        config.translation.backend = defaults.translation.backend
    selected_provider_id = config.translation.llm_provider_id
    normalized_providers: list[LlmProviderConfig] = []
    used_provider_ids: set[str] = set()
    for index, candidate in enumerate(config.translation.llm_providers, start=1):
        if not isinstance(candidate, LlmProviderConfig):
            continue
        provider = copy.deepcopy(candidate)
        original_id = provider.id.strip()
        provider_id = original_id or f"llm-{index}"
        if original_id == "llama-cpp" and provider.name.strip() == "llama.cpp":
            provider_id = "openai"
            provider.name = "OpenAI"
            if selected_provider_id == original_id:
                selected_provider_id = provider_id
        if provider_id in used_provider_ids:
            suffix = 2
            while f"{provider_id}-{suffix}" in used_provider_ids:
                suffix += 1
            provider_id = f"{provider_id}-{suffix}"
        used_provider_ids.add(provider_id)
        provider.id = provider_id
        provider.name = provider.name.strip() or "OpenAI"
        provider.provider_type = "openai_compatible"
        provider.base_url = provider.base_url.strip().rstrip("/")
        provider.model = provider.model.strip()
        provider.api_key = provider.api_key.strip()
        normalized_providers.append(provider)
    if not normalized_providers:
        normalized_providers = default_llm_providers()
    config.translation.llm_providers = normalized_providers
    if selected_provider_id not in {
        provider.id for provider in normalized_providers
    }:
        selected_provider_id = normalized_providers[0].id
    config.translation.llm_provider_id = selected_provider_id
    if config.translation.deepl_api_plan not in {"free", "pro"}:
        config.translation.deepl_api_plan = defaults.translation.deepl_api_plan
    config.translation.timeout_ms = int(
        _clamp(config.translation.timeout_ms, 1000, 120000)
    )
    config.translation.context_segments = int(
        _clamp(config.translation.context_segments, 0, 12)
    )
    config.translation.context_chars = int(
        _clamp(config.translation.context_chars, 0, 12000)
    )
    config.translation.prompt_template = normalize_prompt_template_placeholders(
        config.translation.prompt_template.strip()
        or DEFAULT_LLM_PROMPT_TEMPLATE
    )

    segmentation = config.segmentation
    segmentation.max_chars = int(_clamp(segmentation.max_chars, 40, 1000))
    segmentation.split_lookback_chars = int(
        _clamp(segmentation.split_lookback_chars, 0, 200)
    )
    segmentation.split_lookahead_chars = int(
        _clamp(segmentation.split_lookahead_chars, 0, 500)
    )
    segmentation.max_seconds = int(_clamp(segmentation.max_seconds, 5, 120))
    segmentation.preview_min_chars = int(
        _clamp(segmentation.preview_min_chars, 0, 100)
    )
    segmentation.preview_interval_ms = int(
        _clamp(segmentation.preview_interval_ms, 100, 10000)
    )
    segmentation.preview_char_delta = int(
        _clamp(segmentation.preview_char_delta, 1, 200)
    )
    segmentation.split_punctuation = bool(segmentation.split_punctuation)

    subtitle = config.subtitle
    if subtitle.theme not in {*SUBTITLE_THEME_PRESETS, "custom"}:
        subtitle.theme = defaults.subtitle.theme
    if subtitle.mode not in {"bilingual", "source", "translation"}:
        subtitle.mode = defaults.subtitle.mode
    minimum_sentences = 2 if subtitle.mode == "bilingual" else 1
    subtitle.max_sentences = int(
        _clamp(subtitle.max_sentences, minimum_sentences, 6)
    )
    _normalize_subtitle_appearance(subtitle)
    subtitle.custom_style = _normalized_subtitle_style(
        subtitle.custom_style,
        subtitle_style_values(subtitle),
    )
    apply_subtitle_theme(subtitle, subtitle.theme)
    subtitle.stay_ms = int(_clamp(subtitle.stay_ms, 0, 60000))
    config.window.width = max(360, config.window.width)
    config.window.height = max(100, config.window.height)


def load_config(
    path: Path | None = None,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
    secret_store: SecretStore = DEFAULT_SECRET_STORE,
) -> tuple[AppConfig, Path]:
    path = path or app_paths.config_file()
    config = AppConfig()
    if path.exists():
        try:
            root = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(root, dict):
                raise ValueError("配置根节点必须是对象")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            backup = path.with_name(f"{path.stem}.invalid{path.suffix}")
            try:
                shutil.copy2(path, backup)
            except OSError:
                pass
            setattr(config, "_load_warning", f"配置文件已损坏，已使用默认设置：{error}")
            return config, path
        for section in (
            "asr",
            "translation",
            "segmentation",
            "subtitle",
            "window",
            "hotkey",
            "debug",
        ):
            values = root.get(section)
            if isinstance(values, dict):
                if section == "asr" and "model_variant" in values:
                    variant = values.get("model_variant")
                    preset_fields = {"model_dir", "encoder", "decoder", "joiner", "tokens"}
                    if (
                        isinstance(variant, str)
                        and variant in MODEL_CATALOG
                        and not preset_fields.intersection(values)
                    ):
                        apply_model_preset(config.asr, variant)
                if section == "translation":
                    if "target_lang" not in values:
                        legacy_target = values.get("deepl_target_lang")
                        if isinstance(legacy_target, str) and legacy_target:
                            values = {**values, "target_lang": legacy_target}
                    raw_providers = values.get("llm_providers")
                    if "prompt_template" not in values:
                        legacy_preference = values.get("preference")
                        if isinstance(legacy_preference, str):
                            values = {
                                **values,
                                "prompt_template": prompt_template_with_preference(
                                    legacy_preference
                                ),
                            }
                    merge_values = {
                        key: value
                        for key, value in values.items()
                        if key not in {"llm_providers", "llama_url", "preference"}
                    }
                    _merge_dataclass(config.translation, merge_values)
                    if isinstance(raw_providers, list):
                        providers = [
                            provider
                            for item in raw_providers
                            if (provider := _llm_provider_from_dict(item)) is not None
                        ]
                        if providers:
                            config.translation.llm_providers = providers
                    else:
                        legacy_url = values.get("llama_url")
                        if isinstance(legacy_url, str) and legacy_url.strip():
                            config.translation.llm_providers[0].base_url = (
                                _legacy_llm_base_url(legacy_url)
                            )
                        legacy_stream = values.get("stream")
                        if isinstance(legacy_stream, bool):
                            config.translation.llm_providers[0].stream = legacy_stream
                if section == "subtitle" and "max_sentences" not in values:
                    legacy_limit = values.get(
                        "max_rows", values.get("max_lines_per_language")
                    )
                    if isinstance(legacy_limit, int):
                        values = {**values, "max_sentences": legacy_limit}
                if section == "subtitle" and values.get("outline_width") == 2.0:
                    values = {**values, "outline_width": 0.1}
                if section == "subtitle" and "line_spacing" not in values:
                    legacy_line_height = values.get("line_height")
                    if isinstance(legacy_line_height, (int, float)) and not isinstance(
                        legacy_line_height, bool
                    ):
                        values = {
                            **values,
                            "line_spacing": round(
                                max(0.0, float(legacy_line_height) - 1.0) * 16
                            ),
                        }
                if section == "subtitle":
                    had_theme = "theme" in values
                    raw_custom_style = values.get("custom_style")
                    merge_values = {
                        key: value
                        for key, value in values.items()
                        if key != "custom_style"
                    }
                    _merge_dataclass(config.subtitle, merge_values)
                    if isinstance(raw_custom_style, dict):
                        config.subtitle.custom_style = raw_custom_style
                    if not had_theme and any(
                        name in values for name in SUBTITLE_STYLE_FIELDS
                    ):
                        config.subtitle.theme = "custom"
                        config.subtitle.custom_style = subtitle_style_values(
                            config.subtitle
                        )
                elif section != "translation":
                    _merge_dataclass(getattr(config, section), values)
    _normalize_config(config)
    try:
        config.translation.deepl_api_key = secret_store.unprotect(
            config.translation.deepl_api_key
        )
    except SecretStoreError as error:
        config.translation.deepl_api_key = ""
        setattr(config, "_load_warning", f"无法读取已保存的 DeepL 密钥：{error}")
    for provider in config.translation.llm_providers:
        try:
            provider.api_key = secret_store.unprotect(provider.api_key)
        except SecretStoreError as error:
            provider.api_key = ""
            setattr(
                config,
                "_load_warning",
                f"无法读取已保存的 {provider.name} 密钥：{error}",
            )
    return config, path


def save_config(
    config: AppConfig,
    path: Path,
    *,
    secret_store: SecretStore = DEFAULT_SECRET_STORE,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    root = asdict(config)
    key = root["translation"]["deepl_api_key"]
    if key:
        root["translation"]["deepl_api_key"] = secret_store.protect(key)
    for provider in root["translation"]["llm_providers"]:
        key = provider["api_key"]
        if key:
            provider["api_key"] = secret_store.protect(key)
    temporary.write_text(
        json.dumps(root, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def clone_config(config: AppConfig) -> AppConfig:
    return copy.deepcopy(config)


def resolve_model_files(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> dict[str, Path]:
    model_dir = resolve_model_dir(config, app_paths=app_paths)
    return {
        name: model_dir / getattr(config.asr, name)
        for name in ("encoder", "decoder", "joiner", "tokens")
    }


def resolve_model_dir(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> Path:
    return app_paths.resolve_data_path(config.asr.model_dir)


def model_is_complete(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> bool:
    if config.asr.precision == "fp32":
        from captions.high_precision_runtime import high_precision_runtime_ready

        return high_precision_runtime_ready(app_paths=app_paths)
    return all(
        path.is_file()
        for path in resolve_model_files(config, app_paths=app_paths).values()
    )


def model_install_key(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> tuple[str, ...]:
    if config.asr.precision == "fp32":
        from captions.high_precision_runtime import high_precision_runtime_dir

        return ("fp32", str(high_precision_runtime_dir(app_paths=app_paths)))
    return (
        "int8",
        config.asr.model_variant,
        str(resolve_model_dir(config, app_paths=app_paths)),
    )


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
