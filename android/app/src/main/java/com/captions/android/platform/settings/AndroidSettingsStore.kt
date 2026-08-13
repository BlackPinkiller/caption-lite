package com.captions.android.platform.settings

import android.content.Context
import com.captions.android.core.session.AppearanceSettings
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.SettingsStore

class AndroidSettingsStore(context: Context) : SettingsStore {
    private val preferences = context.getSharedPreferences("captions_settings", Context.MODE_PRIVATE)

    override fun loadAppearance(): AppearanceSettings = AppearanceSettings(
        displayMode = enumValue(
            preferences.getString(KEY_DISPLAY_MODE, null),
            DisplayMode.Bilingual,
        ),
        fontChoice = enumValue(
            preferences.getString(KEY_FONT_CHOICE, null),
            FontChoice.System,
        ),
        sourceSizeSp = preferences.getInt(KEY_SOURCE_SIZE, 15).coerceIn(12, 40),
        translationSizeSp = preferences.getInt(KEY_TRANSLATION_SIZE, 17).coerceIn(12, 40),
    )

    override fun saveAppearance(settings: AppearanceSettings) {
        preferences.edit()
            .putString(KEY_DISPLAY_MODE, settings.displayMode.name)
            .putString(KEY_FONT_CHOICE, settings.fontChoice.name)
            .putInt(KEY_SOURCE_SIZE, settings.sourceSizeSp)
            .putInt(KEY_TRANSLATION_SIZE, settings.translationSizeSp)
            .apply()
    }

    override fun loadRecognitionEngine(): RecognitionEngine = enumValue(
        preferences.getString(KEY_RECOGNITION_ENGINE, null),
        RecognitionEngine.Nemotron,
    )

    override fun saveRecognitionEngine(engine: RecognitionEngine) {
        preferences.edit().putString(KEY_RECOGNITION_ENGINE, engine.name).apply()
    }

    override fun loadTranslation(): TranslationSettings = TranslationSettings(
        enabled = preferences.getBoolean(KEY_TRANSLATION_ENABLED, true),
        sourceLanguage = preferences.getString(KEY_SOURCE_LANGUAGE, "en") ?: "en",
        targetLanguage = preferences.getString(KEY_TARGET_LANGUAGE, "zh") ?: "zh",
    )

    override fun saveTranslation(settings: TranslationSettings) {
        preferences.edit()
            .putBoolean(KEY_TRANSLATION_ENABLED, settings.enabled)
            .putString(KEY_SOURCE_LANGUAGE, settings.sourceLanguage)
            .putString(KEY_TARGET_LANGUAGE, settings.targetLanguage)
            .apply()
    }

    private inline fun <reified T : Enum<T>> enumValue(value: String?, fallback: T): T =
        value?.let { runCatching { enumValueOf<T>(it) }.getOrNull() } ?: fallback

    private companion object {
        const val KEY_DISPLAY_MODE = "display_mode"
        const val KEY_FONT_CHOICE = "font_choice"
        const val KEY_SOURCE_SIZE = "source_size"
        const val KEY_TRANSLATION_SIZE = "translation_size"
        const val KEY_RECOGNITION_ENGINE = "recognition_engine"
        const val KEY_TRANSLATION_ENABLED = "translation_enabled"
        const val KEY_SOURCE_LANGUAGE = "translation_source_language"
        const val KEY_TARGET_LANGUAGE = "translation_target_language"
    }
}
