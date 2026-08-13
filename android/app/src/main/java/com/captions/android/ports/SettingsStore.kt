package com.captions.android.ports

import com.captions.android.core.session.AppearanceSettings
import com.captions.android.core.session.RecognitionEngine

interface SettingsStore {
    fun loadAppearance(): AppearanceSettings
    fun saveAppearance(settings: AppearanceSettings)
    fun loadRecognitionEngine(): RecognitionEngine
    fun saveRecognitionEngine(engine: RecognitionEngine)
}
