package com.captions.android.ports

import com.captions.android.core.session.AppearanceSettings
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.TranslationSettings

interface SettingsStore {
    fun loadAppearance(): AppearanceSettings
    fun saveAppearance(settings: AppearanceSettings)
    fun loadRecognitionEngine(): RecognitionEngine
    fun saveRecognitionEngine(engine: RecognitionEngine)
    fun loadTranslation(): TranslationSettings
    fun saveTranslation(settings: TranslationSettings)
}
