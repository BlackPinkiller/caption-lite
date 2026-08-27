package com.captions.android.core.session

import com.captions.android.core.recognition.PunctuationMode
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

    @Test
    fun `nemotron keeps recognition and translation source in english`() {
        val settings = MemorySettingsStore(
            recognitionEngine = RecognitionEngine.AndroidSystem,
            translation = TranslationSettings(sourceLanguage = "ja", targetLanguage = "en"),
        )
        val store = SessionStore(settings)

        store.setRecognitionEngine(RecognitionEngine.Nemotron)

        assertEquals("en", store.state.value.translationSettings.sourceLanguage)
        assertEquals("ja", store.state.value.translationSettings.targetLanguage)
        assertEquals(store.state.value.translationSettings, settings.translation)
    }

    @Test
    fun `system recognition preserves the selected source language`() {
        val settings = MemorySettingsStore(
            recognitionEngine = RecognitionEngine.AndroidSystem,
            translation = TranslationSettings(sourceLanguage = "ja", targetLanguage = "zh"),
        )

        assertEquals("ja", SessionStore(settings).state.value.translationSettings.sourceLanguage)
    }

    @Test
    fun `nemotron rejects an incompatible source language update`() {
        val store = SessionStore(MemorySettingsStore())

        store.setTranslationSettings(
            TranslationSettings(sourceLanguage = "ja", targetLanguage = "zh"),
        )

        assertEquals("en", store.state.value.translationSettings.sourceLanguage)
        assertEquals("zh", store.state.value.translationSettings.targetLanguage)
    }

    @Test
    fun `punctuation mode defaults off and persists all choices`() {
        val settings = MemorySettingsStore()
        val store = SessionStore(settings)

        assertEquals(PunctuationMode.Off, store.state.value.punctuationMode)
        store.setPunctuationMode(PunctuationMode.All)

        assertEquals(PunctuationMode.All, store.state.value.punctuationMode)
        assertEquals(PunctuationMode.All, settings.punctuationMode)
    }

    @Test
    fun `nemotron model selection updates state and persists`() {
        val settings = MemorySettingsStore()
        val store = SessionStore(settings)

        store.setNemotronModel(NemotronModel.English1120Ms)

        assertEquals(NemotronModel.English1120Ms, store.state.value.nemotronModel)
        assertEquals(NemotronModel.English1120Ms, settings.nemotronModel)
    }

    private class MemorySettingsStore(
        private var recognitionEngine: RecognitionEngine = RecognitionEngine.Nemotron,
        var translation: TranslationSettings = TranslationSettings(),
    ) : SettingsStore {
        var appearance = AppearanceSettings()
        var punctuationMode = PunctuationMode.Off
        var nemotronModel = NemotronModel.English560Ms

        override fun loadAppearance(): AppearanceSettings = appearance

        override fun saveAppearance(settings: AppearanceSettings) {
            appearance = settings
        }

        override fun loadRecognitionEngine(): RecognitionEngine = recognitionEngine

        override fun saveRecognitionEngine(engine: RecognitionEngine) {
            recognitionEngine = engine
        }

        override fun loadNemotronModel(): NemotronModel = nemotronModel

        override fun saveNemotronModel(model: NemotronModel) {
            nemotronModel = model
        }

        override fun loadPunctuationMode(): PunctuationMode = punctuationMode

        override fun savePunctuationMode(mode: PunctuationMode) {
            punctuationMode = mode
        }

        override fun loadTranslation(): TranslationSettings = translation

        override fun saveTranslation(settings: TranslationSettings) {
            translation = settings
        }
    }
}
