package com.captions.android.core.translation

const val DEFAULT_LLM_PROMPT = """源语言：{src}
目标语言：{dst}
翻译下面未完成或完整的字幕。
只输出当前文本的译文，不要解释，不要续写或补全尚未说出的内容。
{ctx}
{terms}

当前文本：
{text}"""

private val PLACEHOLDERS = Regex("\\{(?:src|dst|ctx|terms|text)}")

fun renderPrompt(template: String, values: Map<String, String>): String {
    val normalized = template.trim().ifEmpty { DEFAULT_LLM_PROMPT }
    require("{text}" in normalized) { "提示词必须保留 {text}" }
    return PLACEHOLDERS.replace(normalized) { match ->
        values[match.value.substring(1, match.value.lastIndex)] ?: ""
    }.trim()
}
