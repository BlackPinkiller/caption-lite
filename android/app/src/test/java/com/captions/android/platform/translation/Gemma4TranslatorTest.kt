package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TranslationInput
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class Gemma4TranslatorTest {
    @Test
    fun sameLanguageReturnsTheSourceWithoutRunningInference() {
        var generated = false
        val translator = Gemma4Translator(
            ready = { error("must not be consulted") },
            generate = { _, _ ->
                generated = true
                error("must not run")
            },
        )

        val result = translator.translate(
            TranslationInput("hello"),
            TranslationSettings(sourceLanguage = "en", targetLanguage = "en"),
        )

        assertEquals("hello", result)
        assertEquals(false, generated)
    }

    @Test
    fun usesTheOfficialPromptAndTrimsTheModelOutput() {
        val translator = Gemma4Translator(
            ready = { true },
            generate = { prompt, maxTokens ->
                assertEquals(Gemma4Translator.MAX_TOKENS, maxTokens)
                assertTrue(prompt.contains("Translate the following text into Chinese"))
                assertTrue(prompt.contains("Hello"))
                "  你好  "
            },
        )

        val result = translator.translate(
            TranslationInput("Hello"),
            TranslationSettings(sourceLanguage = "en", targetLanguage = "zh"),
        )

        assertEquals("你好", result)
    }

    @Test
    fun passesSubtitleContextIntoThePrompt() {
        val translator = Gemma4Translator(
            ready = { true },
            generate = { prompt, _ ->
                assertTrue(prompt.contains("[Background Information]"))
                assertTrue(prompt.contains("earlier"))
                "你好"
            },
        )

        val result = translator.translate(
            TranslationInput("current", listOf("earlier")),
            TranslationSettings(sourceLanguage = "en", targetLanguage = "zh"),
        )

        assertEquals("你好", result)
    }

    @Test
    fun failsWhenTheModelIsNotReady() {
        val translator = Gemma4Translator(
            ready = { false },
            generate = { _, _ -> error("must not run") },
        )

        val error = runCatching {
            translator.translate(
                TranslationInput("Hello"),
                TranslationSettings(sourceLanguage = "en", targetLanguage = "zh"),
            )
        }.exceptionOrNull()

        assertTrue(error is IllegalStateException)
        assertTrue(error?.message.orEmpty().contains("尚未就绪"))
    }
}
