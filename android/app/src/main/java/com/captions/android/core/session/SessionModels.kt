package com.captions.android.core.session

import com.captions.android.core.recognition.PunctuationMode

enum class DisplayMode {
    Bilingual,
    Source,
    Translation,
}

enum class FontChoice {
    System,
    Serif,
    Monospace,
}

enum class OverlayPosition {
    Free,
    Top,
    Bottom,
}

enum class RecognitionEngine {
    Nemotron,
    AndroidSystem,
}

enum class NemotronModel {
    English560Ms,
    English1120Ms,
}

enum class TranslationEngine {
    GoogleOnDevice,
    Google2,
    DeepL,
    OpenAICompatible,
    Gemma4,
}

data class TranslationSettings(
    val enabled: Boolean = true,
    val engine: TranslationEngine = TranslationEngine.GoogleOnDevice,
    val sourceLanguage: String = "en",
    val targetLanguage: String = "zh",
    val deeplApiKey: String = "",
    val deeplPro: Boolean = false,
    val timeoutMillis: Int = 15_000,
    val llmBaseUrl: String = "https://api.openai.com/v1",
    val llmModel: String = "",
    val llmApiKey: String = "",
    val llmPromptTemplate: String = com.captions.android.core.translation.DEFAULT_LLM_PROMPT,
    val contextSegments: Int = 3,
)

fun TranslationSettings.forRecognitionEngine(engine: RecognitionEngine): TranslationSettings {
    if (engine != RecognitionEngine.Nemotron || sourceLanguage == "en") return this
    return copy(
        sourceLanguage = "en",
        targetLanguage = if (targetLanguage == "en") sourceLanguage else targetLanguage,
    )
}

data class AppearanceSettings(
    val displayMode: DisplayMode = DisplayMode.Bilingual,
    val fontChoice: FontChoice = FontChoice.System,
    val sourceSizeSp: Int = 15,
    val translationSizeSp: Int = 17,
    val overlayEnabled: Boolean = false,
    val overlayBackgroundEnabled: Boolean = true,
    val overlayPosition: OverlayPosition = OverlayPosition.Bottom,
)

data class SessionEntry(
    val cueId: Long,
    val source: String,
    val translation: String = "",
    val current: Boolean = false,
)

data class SessionUiState(
    val running: Boolean = false,
    val starting: Boolean = false,
    val microphoneEnabled: Boolean = true,
    val displayMode: DisplayMode = DisplayMode.Bilingual,
    val fontChoice: FontChoice = FontChoice.System,
    val sourceSizeSp: Int = 15,
    val translationSizeSp: Int = 17,
    val overlayEnabled: Boolean = false,
    val overlayBackgroundEnabled: Boolean = true,
    val overlayPosition: OverlayPosition = OverlayPosition.Bottom,
    val recognitionEngine: RecognitionEngine = RecognitionEngine.Nemotron,
    val nemotronModel: NemotronModel = NemotronModel.English560Ms,
    val punctuationMode: PunctuationMode = PunctuationMode.Off,
    val translationSettings: TranslationSettings = TranslationSettings(),
    val entries: List<SessionEntry> = emptyList(),
    val message: String = "",
)
