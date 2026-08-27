package com.captions.android.platform.settings

import android.content.Context
import com.captions.android.core.session.AppearanceSettings
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.OverlayPosition
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.NemotronModel
import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.recognition.PunctuationMode
import com.captions.android.ports.SettingsStore
import com.captions.android.platform.security.AndroidSecretStore

internal fun resolvePunctuationMode(
    storedMode: String?,
    legacyEnabled: Boolean?,
): PunctuationMode {
    if (storedMode != null) {
        return runCatching { enumValueOf<PunctuationMode>(storedMode) }
            .getOrDefault(PunctuationMode.Off)
    }
    return if (legacyEnabled == true) PunctuationMode.Sentence else PunctuationMode.Off
}

class AndroidSettingsStore(context: Context) : SettingsStore {
    private val preferences = context.getSharedPreferences("captions_settings", Context.MODE_PRIVATE)
    private val secretStore = AndroidSecretStore(context)

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
        overlayEnabled = preferences.getBoolean(KEY_OVERLAY_ENABLED, false),
        overlayBackgroundEnabled = preferences.getBoolean(KEY_OVERLAY_BACKGROUND, true),
        overlayPosition = enumValue(
            preferences.getString(KEY_OVERLAY_POSITION, null),
            OverlayPosition.Bottom,
        ),
    )

    override fun saveAppearance(settings: AppearanceSettings) {
        preferences.edit()
            .putString(KEY_DISPLAY_MODE, settings.displayMode.name)
            .putString(KEY_FONT_CHOICE, settings.fontChoice.name)
            .putInt(KEY_SOURCE_SIZE, settings.sourceSizeSp)
            .putInt(KEY_TRANSLATION_SIZE, settings.translationSizeSp)
            .putBoolean(KEY_OVERLAY_ENABLED, settings.overlayEnabled)
            .putBoolean(KEY_OVERLAY_BACKGROUND, settings.overlayBackgroundEnabled)
            .putString(KEY_OVERLAY_POSITION, settings.overlayPosition.name)
            .apply()
    }

    override fun loadRecognitionEngine(): RecognitionEngine = enumValue(
        preferences.getString(KEY_RECOGNITION_ENGINE, null),
        RecognitionEngine.Nemotron,
    )

    override fun saveRecognitionEngine(engine: RecognitionEngine) {
        preferences.edit().putString(KEY_RECOGNITION_ENGINE, engine.name).apply()
    }

    override fun loadNemotronModel(): NemotronModel = enumValue(
        preferences.getString(KEY_NEMOTRON_MODEL, null),
        NemotronModel.English560Ms,
    )

    override fun saveNemotronModel(model: NemotronModel) {
        preferences.edit().putString(KEY_NEMOTRON_MODEL, model.name).apply()
    }

    override fun loadPunctuationMode(): PunctuationMode {
        val stored = preferences.getString(KEY_PUNCTUATION_MODE, null)
        val legacy = if (preferences.contains(KEY_SPLIT_PUNCTUATION)) {
            preferences.getBoolean(KEY_SPLIT_PUNCTUATION, false)
        } else null
        return resolvePunctuationMode(stored, legacy)
    }

    override fun savePunctuationMode(mode: PunctuationMode) {
        preferences.edit()
            .putString(KEY_PUNCTUATION_MODE, mode.name)
            .remove(KEY_SPLIT_PUNCTUATION)
            .apply()
    }

    override fun loadTranslation(): TranslationSettings = TranslationSettings(
        enabled = preferences.getBoolean(KEY_TRANSLATION_ENABLED, true),
        engine = enumValue(
            preferences.getString(KEY_TRANSLATION_ENGINE, null),
            TranslationEngine.GoogleOnDevice,
        ),
        sourceLanguage = preferences.getString(KEY_SOURCE_LANGUAGE, "en") ?: "en",
        targetLanguage = preferences.getString(KEY_TARGET_LANGUAGE, "zh") ?: "zh",
        deeplApiKey = secretStore.read(KEY_DEEPL_API_KEY),
        deeplPro = preferences.getBoolean(KEY_DEEPL_PRO, false),
        timeoutMillis = preferences.getInt(KEY_TRANSLATION_TIMEOUT, 15_000)
            .coerceIn(3_000, 120_000),
        llmBaseUrl = preferences.getString(KEY_LLM_BASE_URL, "https://api.openai.com/v1")
            ?: "https://api.openai.com/v1",
        llmModel = preferences.getString(KEY_LLM_MODEL, "") ?: "",
        llmApiKey = secretStore.read(KEY_LLM_API_KEY),
        llmPromptTemplate = preferences.getString(
            KEY_LLM_PROMPT,
            com.captions.android.core.translation.DEFAULT_LLM_PROMPT,
        ) ?: com.captions.android.core.translation.DEFAULT_LLM_PROMPT,
        contextSegments = preferences.getInt(KEY_CONTEXT_SEGMENTS, 3).coerceIn(0, 12),
    )

    override fun saveTranslation(settings: TranslationSettings) {
        preferences.edit()
            .putBoolean(KEY_TRANSLATION_ENABLED, settings.enabled)
            .putString(KEY_TRANSLATION_ENGINE, settings.engine.name)
            .putString(KEY_SOURCE_LANGUAGE, settings.sourceLanguage)
            .putString(KEY_TARGET_LANGUAGE, settings.targetLanguage)
            .putBoolean(KEY_DEEPL_PRO, settings.deeplPro)
            .putInt(KEY_TRANSLATION_TIMEOUT, settings.timeoutMillis)
            .putString(KEY_LLM_BASE_URL, settings.llmBaseUrl.trim())
            .putString(KEY_LLM_MODEL, settings.llmModel.trim())
            .putString(KEY_LLM_PROMPT, settings.llmPromptTemplate)
            .putInt(KEY_CONTEXT_SEGMENTS, settings.contextSegments.coerceIn(0, 12))
            .apply()
        secretStore.write(KEY_DEEPL_API_KEY, settings.deeplApiKey.trim())
        secretStore.write(KEY_LLM_API_KEY, settings.llmApiKey.trim())
    }

    private inline fun <reified T : Enum<T>> enumValue(value: String?, fallback: T): T =
        value?.let { runCatching { enumValueOf<T>(it) }.getOrNull() } ?: fallback

    private companion object {
        const val KEY_DISPLAY_MODE = "display_mode"
        const val KEY_FONT_CHOICE = "font_choice"
        const val KEY_SOURCE_SIZE = "source_size"
        const val KEY_TRANSLATION_SIZE = "translation_size"
        const val KEY_OVERLAY_ENABLED = "overlay_enabled"
        const val KEY_OVERLAY_BACKGROUND = "overlay_background"
        const val KEY_OVERLAY_POSITION = "overlay_position"
        const val KEY_RECOGNITION_ENGINE = "recognition_engine"
        const val KEY_NEMOTRON_MODEL = "nemotron_model"
        const val KEY_PUNCTUATION_MODE = "punctuation_mode"
        const val KEY_SPLIT_PUNCTUATION = "split_punctuation"
        const val KEY_TRANSLATION_ENABLED = "translation_enabled"
        const val KEY_TRANSLATION_ENGINE = "translation_engine"
        const val KEY_SOURCE_LANGUAGE = "translation_source_language"
        const val KEY_TARGET_LANGUAGE = "translation_target_language"
        const val KEY_DEEPL_API_KEY = "deepl_api_key"
        const val KEY_DEEPL_PRO = "deepl_pro"
        const val KEY_TRANSLATION_TIMEOUT = "translation_timeout"
        const val KEY_LLM_BASE_URL = "llm_base_url"
        const val KEY_LLM_MODEL = "llm_model"
        const val KEY_LLM_API_KEY = "llm_api_key"
        const val KEY_LLM_PROMPT = "llm_prompt"
        const val KEY_CONTEXT_SEGMENTS = "translation_context_segments"
    }
}
