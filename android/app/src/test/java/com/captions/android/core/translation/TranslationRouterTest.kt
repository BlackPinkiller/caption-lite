package com.captions.android.core.translation

import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TranslationRouterTest {
    @Test
    fun selectsOnlyTheConfiguredBackend() {
        val router = TranslationRouter(
            local = named("local"),
            google2 = named("google"),
            deepL = named("deepl"),
            openAICompatible = named("llm"),
            gemma4 = named("gemma4"),
        )

        TranslationEngine.entries.forEach { engine ->
            val expected = when (engine) {
                TranslationEngine.GoogleOnDevice -> "local"
                TranslationEngine.Google2 -> "google"
                TranslationEngine.DeepL -> "deepl"
                TranslationEngine.OpenAICompatible -> "llm"
                TranslationEngine.Gemma4 -> "gemma4"
            }
            assertEquals(
                expected,
                router.translate(TranslationInput("text"), TranslationSettings(engine = engine)),
            )
        }
    }

    @Test
    fun closeReleasesEveryBackend() {
        val translators = List(5) { TrackingTranslator() }
        val router = TranslationRouter(
            local = translators[0],
            google2 = translators[1],
            deepL = translators[2],
            openAICompatible = translators[3],
            gemma4 = translators[4],
        )

        router.close()

        assertTrue(translators.all { it.closed })
    }

    private fun named(name: String) = TextTranslator { _, _ -> name }

    private class TrackingTranslator : TextTranslator {
        var closed = false

        override fun translate(
            input: TranslationInput,
            settings: TranslationSettings,
        ): String = input.text

        override fun close() {
            closed = true
        }
    }
}
