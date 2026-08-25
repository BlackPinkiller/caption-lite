package com.captions.android.core.translation

/**
 * Builds the official HyMT2 translation prompt. Follows the model card's
 * default format (and its "background information" variant when subtitle
 * context is available). Chinese prompts use Chinese language names, English
 * prompts use English language names.
 */
object HyMt2Prompt {
    private val CHINESE_NAMES = mapOf(
        "en" to "英语",
        "zh" to "中文",
        "zh-Hant" to "繁体中文",
        "ja" to "日语",
        "ko" to "韩语",
        "de" to "德语",
        "fr" to "法语",
        "es" to "西班牙语",
        "it" to "意大利语",
        "pt" to "葡萄牙语",
        "ru" to "俄语",
    )

    private val ENGLISH_NAMES = mapOf(
        "en" to "English",
        "zh" to "Chinese",
        "zh-Hant" to "Traditional Chinese",
        "ja" to "Japanese",
        "ko" to "Korean",
        "de" to "German",
        "fr" to "French",
        "es" to "Spanish",
        "it" to "Italian",
        "pt" to "Portuguese",
        "ru" to "Russian",
    )

    fun build(
        sourceLanguage: String,
        targetLanguage: String,
        text: String,
        context: List<String>,
    ): String {
        val chinesePrompt = sourceLanguage.substringBefore('-').equals("zh", ignoreCase = true)
        val target = if (chinesePrompt) {
            CHINESE_NAMES[targetLanguage] ?: targetLanguage
        } else {
            ENGLISH_NAMES[targetLanguage] ?: targetLanguage
        }
        val background = context.joinToString("\n").trim()
        return if (background.isEmpty()) {
            if (chinesePrompt) {
                "将以下文本翻译为 $target，注意只需要输出翻译后的结果，不要额外解释：\n\n$text"
            } else {
                "Translate the following text into $target. Note that you should " +
                    "only output the translated result without any additional explanation:\n\n$text"
            }
        } else {
            if (chinesePrompt) {
                "【背景信息】\n$background\n\n请结合背景信息将以下文本翻译为 $target。\n\n【待翻译文本】\n$text"
            } else {
                "[Background Information]\n$background\n\nPlease translate the following text " +
                    "into $target, taking the provided background information into consideration.\n\n" +
                    "[Source Text]\n$text"
            }
        }
    }
}
