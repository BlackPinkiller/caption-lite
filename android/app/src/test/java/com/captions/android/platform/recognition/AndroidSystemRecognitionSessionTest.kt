package com.captions.android.platform.recognition

import org.junit.Assert.assertEquals
import org.junit.Test

class AndroidSystemRecognitionSessionTest {
    @Test
    fun `recognition uses the selected language tag`() {
        assertEquals("en", recognitionLanguageTag("en"))
        assertEquals("zh", recognitionLanguageTag("zh"))
        assertEquals("ja", recognitionLanguageTag("ja"))
    }

    @Test
    fun `language support accepts a matching regional model`() {
        assertEquals(true, supportsLanguage("en", listOf("en-US", "zh-CN")))
        assertEquals(true, supportsLanguage("zh", listOf("zh-TW")))
        assertEquals(false, supportsLanguage("ja", listOf("en-US", "zh-CN")))
        assertEquals("en-US", matchingLanguage("en", listOf("en-US", "en-GB")))
    }
}
