from __future__ import annotations

import re


PROMPT_PLACEHOLDERS = (
    "src",
    "dst",
    "ctx",
    "terms",
    "text",
)
PROMPT_PLACEHOLDER_TOKENS = tuple(
    f"{{{name}}}" for name in PROMPT_PLACEHOLDERS
)
PROMPT_PLACEHOLDER_PATTERN = re.compile(
    r"\{(?:" + "|".join(PROMPT_PLACEHOLDERS) + r")\}"
)

DEFAULT_LLM_PROMPT_TEMPLATE = """源语言：{src}
目标语言：{dst}
翻译下面未完成或完整的字幕。
只输出当前文本的译文，不要解释，不要续写或补全尚未说出的内容。
{ctx}
{terms}

当前文本：
{text}"""

LEGACY_PROMPT_PLACEHOLDERS = {
    "{source_language}": "{src}",
    "{target_language}": "{dst}",
    "{context}": "{ctx}",
    "{glossary}": "{terms}",
}


def normalize_prompt_template_placeholders(template: str) -> str:
    for old, new in LEGACY_PROMPT_PLACEHOLDERS.items():
        template = template.replace(old, new)
    return template


def prompt_template_with_preference(preference: str) -> str:
    preference = preference.strip()
    if not preference:
        return DEFAULT_LLM_PROMPT_TEMPLATE
    return DEFAULT_LLM_PROMPT_TEMPLATE.replace(
        "{ctx}",
        f"翻译偏好：{preference}\n{{ctx}}",
    )


def render_prompt_template(template: str, values: dict[str, str]) -> str:
    template = template.strip() or DEFAULT_LLM_PROMPT_TEMPLATE
    if "{text}" not in template:
        raise ValueError("提示词模板必须包含 {text} 占位符")

    def replace(match: re.Match[str]) -> str:
        return values.get(match.group(0)[1:-1], "")

    return PROMPT_PLACEHOLDER_PATTERN.sub(replace, template).strip()
