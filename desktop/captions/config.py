from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from captions.core.config_normalization import _normalize_config
from captions.core.model_catalog import MODEL_CATALOG, apply_model_preset
from captions.core.prompt_template import prompt_template_with_preference
from captions.core.settings import AppConfig, LlmProviderConfig, _merge_dataclass
from captions.core.subtitle_style import SUBTITLE_STYLE_FIELDS, subtitle_style_values
from captions.platforms.portable_paths import DEFAULT_APP_PATHS
from captions.platforms.secret_store import DEFAULT_SECRET_STORE
from captions.ports.app_paths import AppPaths
from captions.ports.secret_store import SecretStore, SecretStoreError


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
                if section == "segmentation":
                    if "punctuation_mode" not in values:
                        legacy_punctuation = values.get("split_punctuation")
                        if isinstance(legacy_punctuation, bool):
                            values = {
                                **values,
                                "punctuation_mode": (
                                    "sentence" if legacy_punctuation else "off"
                                ),
                            }
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
        config.translation.google2_api_key = secret_store.unprotect(
            config.translation.google2_api_key
        )
    except SecretStoreError:
        config.translation.google2_api_key = ""
        setattr(config, "_load_warning", "无法读取已保存的 Google2 密钥，将按需重新获取")
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
    key = root["translation"]["google2_api_key"]
    if key:
        try:
            root["translation"]["google2_api_key"] = secret_store.protect(key)
        except SecretStoreError:
            # Platforms without secure storage may keep the component key in
            # memory and obtain it again next time; never fall back to plaintext.
            root["translation"]["google2_api_key"] = ""
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
