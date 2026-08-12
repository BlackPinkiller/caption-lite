from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


MODEL_NAME = "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25"
MULTILINGUAL_MODEL_NAME = (
    "sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-560ms-int8-2026-06-11"
)
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{MODEL_NAME}.tar.bz2"
)
MULTILINGUAL_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{MULTILINGUAL_MODEL_NAME}.tar.bz2"
)
MODEL_PRESETS = {
    "english": (MODEL_NAME, MODEL_URL),
    "multilingual": (MULTILINGUAL_MODEL_NAME, MULTILINGUAL_MODEL_URL),
}


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_resource_path(name: str) -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", application_dir()))
    return bundle_root / "resources" / name


@dataclass
class AsrConfig:
    model_variant: str = "english"
    model_dir: str = f"models/{MODEL_NAME}"
    encoder: str = "encoder.int8.onnx"
    decoder: str = "decoder.int8.onnx"
    joiner: str = "joiner.int8.onnx"
    tokens: str = "tokens.txt"
    language: str = "auto"
    auto_standby_seconds: int = 0


@dataclass
class TranslationConfig:
    backend: str = "llama"
    source_lang: str = "EN"
    target_lang: str = "ZH-HANS"
    llama_url: str = "http://127.0.0.1:8080/v1/chat/completions"
    deepl_api_key: str = ""
    deepl_api_plan: str = "free"
    timeout_ms: int = 15000
    stream: bool = True
    context_segments: int = 3
    context_chars: int = 1200
    preference: str = ""
    glossary: dict[str, str] = field(default_factory=dict)


@dataclass
class SegmentationConfig:
    max_chars: int = 160
    split_lookback_chars: int = 32
    split_lookahead_chars: int = 160
    max_seconds: int = 20
    preview_min_chars: int = 6
    preview_interval_ms: int = 900
    preview_char_delta: int = 18


@dataclass
class SubtitleConfig:
    mode: str = "bilingual"
    max_rows: int = 2
    font_family: str = "Microsoft YaHei UI"
    source_size: int = 30
    translation_size: int = 32
    font_weight: int = 600
    text_color: str = "#ffffff"
    outline_color: str = "#000000"
    outline_width: float = 2.0
    shadow: bool = True
    line_height: float = 1.25
    align: str = "center"
    background: str = "line"
    background_color: str = "rgba(0,0,0,0.62)"
    padding: int = 12
    old_opacity: float = 0.68
    preview_opacity: float = 0.86
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
class AppConfig:
    asr: AsrConfig = field(default_factory=AsrConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)


def _merge_dataclass(instance: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if hasattr(instance, key):
            setattr(instance, key, value)


def load_config(path: Path | None = None) -> tuple[AppConfig, Path]:
    path = path or application_dir() / "config.json"
    config = AppConfig()
    if path.exists():
        root = json.loads(path.read_text(encoding="utf-8-sig"))
        for section in (
            "asr",
            "translation",
            "segmentation",
            "subtitle",
            "window",
            "hotkey",
        ):
            values = root.get(section)
            if isinstance(values, dict):
                if section == "translation" and "target_lang" not in values:
                    legacy_target = values.get("deepl_target_lang")
                    if isinstance(legacy_target, str) and legacy_target:
                        values = {**values, "target_lang": legacy_target}
                if section == "subtitle" and "max_rows" not in values:
                    legacy_rows = values.get("max_lines_per_language")
                    if isinstance(legacy_rows, int):
                        values = {**values, "max_rows": legacy_rows}
                _merge_dataclass(getattr(config, section), values)
    return config, path


def save_config(config: AppConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def clone_config(config: AppConfig) -> AppConfig:
    return copy.deepcopy(config)


def resolve_model_files(config: AppConfig) -> dict[str, Path]:
    model_dir = resolve_model_dir(config)
    return {
        name: model_dir / getattr(config.asr, name)
        for name in ("encoder", "decoder", "joiner", "tokens")
    }


def resolve_model_dir(config: AppConfig) -> Path:
    model_dir = Path(config.asr.model_dir)
    if not model_dir.is_absolute():
        model_dir = application_dir() / model_dir
    return model_dir


def model_is_complete(config: AppConfig) -> bool:
    return all(path.is_file() for path in resolve_model_files(config).values())


def model_download_spec(config: AppConfig) -> tuple[str, str]:
    return MODEL_PRESETS.get(config.asr.model_variant, MODEL_PRESETS["english"])


def default_model_dir(model_variant: str) -> str:
    name, _ = MODEL_PRESETS.get(model_variant, MODEL_PRESETS["english"])
    return f"models/{name}"
