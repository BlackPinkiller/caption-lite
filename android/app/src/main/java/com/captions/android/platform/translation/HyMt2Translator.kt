package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.translation.HyMt2Prompt
import com.captions.android.hymt.HyMt2Engine
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput

class HyMt2Translator(
    private val ready: (TranslationSettings) -> Boolean,
    private val generate: (prompt: String, maxTokens: Int) -> String,
) : TextTranslator {
    override fun translate(input: TranslationInput, settings: TranslationSettings): String {
        if (sameLanguage(settings.sourceLanguage, settings.targetLanguage)) return input.text
        check(ready(settings)) { "HyMT2 模型尚未就绪" }
        val prompt = HyMt2Prompt.build(
            sourceLanguage = settings.sourceLanguage,
            targetLanguage = settings.targetLanguage,
            text = input.text,
            context = input.context,
        )
        return generate(prompt, MAX_TOKENS).trim()
    }

    override fun close() = Unit

    companion object {
        const val MAX_TOKENS = 256
    }
}

fun hyMt2Translator(modelManager: HyMt2ModelManager): HyMt2Translator =
    HyMt2Translator(modelManager::isReady, HyMt2Engine::generate)
