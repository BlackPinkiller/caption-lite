package com.captions.android.ports

import com.captions.android.core.session.AppearanceSettings
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.NemotronModel
import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.recognition.PunctuationMode

interface SettingsStore {
    fun loadAppearance(): AppearanceSettings
    fun saveAppearance(settings: AppearanceSettings)
    fun loadRecognitionEngine(): RecognitionEngine
    fun saveRecognitionEngine(engine: RecognitionEngine)
    fun loadNemotronModel(): NemotronModel
    fun saveNemotronModel(model: NemotronModel)
    fun loadPunctuationMode(): PunctuationMode
    fun savePunctuationMode(mode: PunctuationMode)
    fun loadTranslation(): TranslationSettings
    fun saveTranslation(settings: TranslationSettings)
}
