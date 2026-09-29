from __future__ import annotations

import copy

from captions.core.model_catalog import MODEL_CATALOG, MODEL_PRESETS, supports_high_precision
from captions.core.settings import AppConfig, LlmProviderConfig, default_llm_providers, _clamp
from captions.core.prompt_template import (
    DEFAULT_LLM_PROMPT_TEMPLATE,
    normalize_prompt_template_placeholders,
)
from captions.core.subtitle_style import (
    SUBTITLE_THEME_PRESETS, _normalize_subtitle_appearance, _normalized_subtitle_style,
    subtitle_style_values, apply_subtitle_theme,
)


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
    if segmentation.punctuation_mode not in {"off", "sentence", "all"}:
        segmentation.punctuation_mode = defaults.segmentation.punctuation_mode

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
    config.window.width_percent = int(_clamp(config.window.width_percent, 30, 90))
    config.window.center_x_ratio = float(_clamp(config.window.center_x_ratio, .05, .95))
    config.window.bottom_ratio = float(_clamp(config.window.bottom_ratio, .05, .95))
