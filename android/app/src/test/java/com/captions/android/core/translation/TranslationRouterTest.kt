package com.captions.android.core.translation

import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput
import org.junit.Assert.assertEquals
import org.junit.Test

class TranslationRouterTest {
    @Test
    fun selectsOnlyTheConfiguredBackend() {
        val router = TranslationRouter(
            local = named("local"),
            google2 = named("google"),
            deepL = named("deepl"),
            openAICompatible = named("llm"),
        )

        TranslationEngine.entries.forEach { engine ->
            val expected = when (engine) {
                TranslationEngine.GoogleOnDevice -> "local"
                TranslationEngine.Google2 -> "google"
                TranslationEngine.DeepL -> "deepl"
                TranslationEngine.OpenAICompatible -> "llm"
            }
            assertEquals(
                expected,
                router.translate(TranslationInput("text"), TranslationSettings(engine = engine)),
            )
        }
    }

    private fun named(name: String) = TextTranslator { _, _ -> name }
}
