from __future__ import annotations

import re
import time
from dataclasses import dataclass

from captions.core.settings import TranslationConfig
from captions.core.prompt_template import render_prompt_template


LANGUAGE_NAMES = {
    "AUTO": "自动识别的语言",
    "EN": "英语",
    "ZH": "中文",
    "ZH-HANS": "简体中文",
    "ZH-HANT": "繁体中文",
    "EN-US": "英语",
    "DE": "德语",
    "FR": "法语",
    "ES": "西班牙语",
    "IT": "意大利语",
    "PT": "葡萄牙语",
    "JA": "日语",
    "KO": "韩语",
    "NL": "荷兰语",
    "RU": "俄语",
}


@dataclass
class HistoryRecord:
    time: str
    source: str
    translation: str
    backend: str
    forced: bool = False


class StaleTranslationError(RuntimeError):
    pass


def translation_queue_expired(
    submitted_at: float, timeout_ms: int, *, now: float | None = None
) -> bool:
    now = time.monotonic() if now is None else now
    maximum_age = max(1.0, timeout_ms / 1000)
    return now - submitted_at > maximum_age


def matching_glossary(glossary: dict[str, str], text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for source, target in glossary.items():
        if re.search(rf"(?<!\w){re.escape(source)}(?!\w)", text, re.IGNORECASE):
            matches.append((source, target))
    return sorted(matches, key=lambda item: len(item[0]), reverse=True)


def build_hymt_prompt(
    current: str, history: list[HistoryRecord], config: TranslationConfig
) -> str:
    context: list[str] = []
    chars = 0
    for item in reversed(history[-config.context_segments :]):
        if chars + len(item.source) > config.context_chars:
            break
        context.insert(0, item.source)
        chars += len(item.source)
    background = "\n".join(context)
    searchable = f"{background}\n{current}"
    source = LANGUAGE_NAMES.get(config.source_lang, config.source_lang)
    target = LANGUAGE_NAMES.get(config.target_lang, config.target_lang)
    terms = matching_glossary(config.glossary, searchable)
    context_block = (
        f"仅供消歧的上文（不要翻译）：\n{background}" if background else ""
    )
    glossary_block = (
        "必须遵守的术语：" + "".join(f"\n{s} = {t}" for s, t in terms)
        if terms
        else ""
    )
    return render_prompt_template(
        config.prompt_template,
        {
            "src": source,
            "dst": target,
            "ctx": context_block,
            "terms": glossary_block,
            "text": current,
        },
    )
