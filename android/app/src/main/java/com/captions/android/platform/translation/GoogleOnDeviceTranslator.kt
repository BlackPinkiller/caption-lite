package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationModelManager
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.nl.translate.Translation
import java.util.concurrent.TimeUnit

class GoogleOnDeviceTranslator(
    private val modelManager: TranslationModelManager,
) : TextTranslator {
    override fun translate(text: String, settings: TranslationSettings): String {
        check(modelManager.isReady(settings)) { "请先下载本地翻译模型" }
        val translator = Translation.getClient(GoogleTranslationModelManager.options(settings))
        return try {
            Tasks.await(translator.translate(text), TRANSLATION_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        } finally {
            translator.close()
        }
    }

    private companion object {
        const val TRANSLATION_TIMEOUT_SECONDS = 30L
    }
}
