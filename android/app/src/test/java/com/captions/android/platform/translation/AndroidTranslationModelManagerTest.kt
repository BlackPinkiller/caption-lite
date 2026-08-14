package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidTranslationModelManagerTest {
    @Test
    fun regionalTagsMatchTheSameLanguage() {
        assertTrue(sameLanguage("en-US", "en"))
        assertTrue(sameLanguage("zh-Hans-CN", "zh"))
        assertFalse(sameLanguage("en", "ja"))
    }

    @Test
    fun settingsPairIgnoresRegionalTagDifferences() {
        val configured = TranslationSettings(
            sourceLanguage = "en-US",
            targetLanguage = "zh-Hans-CN",
        )

        assertTrue(
            configured.samePair(
                TranslationSettings(sourceLanguage = "en", targetLanguage = "zh"),
            ),
        )
        assertFalse(
            configured.samePair(
                TranslationSettings(sourceLanguage = "en", targetLanguage = "ja"),
            ),
        )
    }
}
