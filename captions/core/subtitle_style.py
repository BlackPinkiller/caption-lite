from __future__ import annotations

import copy
from typing import Any

from captions.core.settings import SubtitleConfig, _clamp, _compatible_value


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
