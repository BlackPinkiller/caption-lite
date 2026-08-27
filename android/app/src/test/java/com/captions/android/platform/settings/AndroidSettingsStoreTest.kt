package com.captions.android.platform.settings

import com.captions.android.core.recognition.PunctuationMode
import org.junit.Assert.assertEquals
import org.junit.Test

class AndroidSettingsStoreTest {
    @Test
    fun newInstallDefaultsPunctuationSegmentationOff() {
        assertEquals(PunctuationMode.Off, resolvePunctuationMode(null, null))
    }

    @Test
    fun legacyBooleanMigratesToEquivalentMode() {
        assertEquals(PunctuationMode.Off, resolvePunctuationMode(null, false))
        assertEquals(PunctuationMode.Sentence, resolvePunctuationMode(null, true))
    }

    @Test
    fun storedModeTakesPriorityAndInvalidValuesAreSafe() {
        assertEquals(PunctuationMode.All, resolvePunctuationMode("All", false))
        assertEquals(PunctuationMode.Off, resolvePunctuationMode("invalid", true))
    }
}
