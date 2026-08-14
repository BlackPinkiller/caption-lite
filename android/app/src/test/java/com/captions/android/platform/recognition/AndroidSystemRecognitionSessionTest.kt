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
}
