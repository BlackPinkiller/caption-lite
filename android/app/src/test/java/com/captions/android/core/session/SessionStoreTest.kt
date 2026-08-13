package com.captions.android.core.session

import com.captions.android.ports.SettingsStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionStoreTest {
    @Test
    fun `overlay settings update state and persist as appearance`() {
        val settings = MemorySettingsStore()
        val store = SessionStore(settings)

        store.setOverlayEnabled(true)
        store.setOverlayBackgroundEnabled(false)
        store.setOverlayPosition(OverlayPosition.Free)

        assertTrue(store.state.value.overlayEnabled)
        assertFalse(store.state.value.overlayBackgroundEnabled)
        assertEquals(OverlayPosition.Free, store.state.value.overlayPosition)
        assertEquals(store.state.value.overlayEnabled, settings.appearance.overlayEnabled)
        assertEquals(
            store.state.value.overlayBackgroundEnabled,
            settings.appearance.overlayBackgroundEnabled,
        )
        assertEquals(store.state.value.overlayPosition, settings.appearance.overlayPosition)
    }

    private class MemorySettingsStore : SettingsStore {
        var appearance = AppearanceSettings()

        override fun loadAppearance(): AppearanceSettings = appearance

        override fun saveAppearance(settings: AppearanceSettings) {
            appearance = settings
        }

        override fun loadRecognitionEngine(): RecognitionEngine = RecognitionEngine.Nemotron

        override fun saveRecognitionEngine(engine: RecognitionEngine) = Unit

        override fun loadTranslation(): TranslationSettings = TranslationSettings()

        override fun saveTranslation(settings: TranslationSettings) = Unit
    }
}
