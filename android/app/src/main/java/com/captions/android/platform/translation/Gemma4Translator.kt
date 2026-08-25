package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.translation.HyMt2Prompt
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput

class Gemma4Translator(
    private val ready: (TranslationSettings) -> Boolean,
    private val generate: (prompt: String, maxTokens: Int) -> String,
) : TextTranslator {
    override fun translate(input: TranslationInput, settings: TranslationSettings): String {
        if (sameLanguage(settings.sourceLanguage, settings.targetLanguage)) return input.text
        check(ready(settings)) { "Gemma 4 模型尚未就绪" }
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

fun gemma4Translator(modelManager: Gemma4ModelManager): Gemma4Translator =
    Gemma4Translator(modelManager::isReady, modelManager::generate)
