package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import org.junit.Assert.assertEquals
import org.junit.Test

class GoogleTranslationModelManagerTest {
    @Test
    fun `english uses only the other language model`() {
        assertEquals(
            setOf("zh"),
            requiredDownloadLanguages(
                TranslationSettings(sourceLanguage = "en", targetLanguage = "zh"),
            ),
        )
    }

    @Test
    fun `two non english languages require both models`() {
        assertEquals(
            setOf("ja", "zh"),
            requiredDownloadLanguages(
                TranslationSettings(sourceLanguage = "ja", targetLanguage = "zh"),
            ),
        )
    }

    @Test
    fun `english is built in`() {
        assertEquals(
            emptySet<String>(),
            requiredDownloadLanguages(
                TranslationSettings(sourceLanguage = "en", targetLanguage = "en"),
            ),
        )
    }
}
