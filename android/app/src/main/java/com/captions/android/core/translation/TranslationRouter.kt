package com.captions.android.core.translation

import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator

class TranslationRouter(
    private val local: TextTranslator,
    private val google2: TextTranslator,
    private val deepL: TextTranslator,
) : TextTranslator {
    override fun translate(text: String, settings: TranslationSettings): String = when (settings.engine) {
        TranslationEngine.GoogleOnDevice -> local.translate(text, settings)
        TranslationEngine.Google2 -> google2.translate(text, settings)
        TranslationEngine.DeepL -> deepL.translate(text, settings)
    }
}
