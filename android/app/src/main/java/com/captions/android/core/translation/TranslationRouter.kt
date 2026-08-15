package com.captions.android.core.translation

import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput

class TranslationRouter(
    private val local: TextTranslator,
    private val google2: TextTranslator,
    private val deepL: TextTranslator,
    private val openAICompatible: TextTranslator,
    private val gemma4: TextTranslator,
) : TextTranslator {
    override fun translate(input: TranslationInput, settings: TranslationSettings): String = when (settings.engine) {
        TranslationEngine.GoogleOnDevice -> local.translate(input, settings)
        TranslationEngine.Google2 -> google2.translate(input, settings)
        TranslationEngine.DeepL -> deepL.translate(input, settings)
        TranslationEngine.OpenAICompatible -> openAICompatible.translate(input, settings)
        TranslationEngine.Gemma4 -> gemma4.translate(input, settings)
    }

    override fun close() {
        local.close()
        google2.close()
        deepL.close()
        openAICompatible.close()
        gemma4.close()
    }
}
