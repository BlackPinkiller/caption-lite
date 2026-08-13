package com.captions.android.core.session

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

enum class RecognitionEngine {
    Nemotron,
    AndroidSystem,
}

enum class TranslationEngine {
    GoogleOnDevice,
    Google2,
    DeepL,
    OpenAICompatible,
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

data class AppearanceSettings(
    val displayMode: DisplayMode = DisplayMode.Bilingual,
    val fontChoice: FontChoice = FontChoice.System,
    val sourceSizeSp: Int = 15,
    val translationSizeSp: Int = 17,
)

data class SessionEntry(
    val cueId: Long,
    val source: String,
    val translation: String = "",
    val current: Boolean = false,
)

data class SessionUiState(
    val running: Boolean = false,
    val microphoneEnabled: Boolean = true,
    val displayMode: DisplayMode = DisplayMode.Bilingual,
    val fontChoice: FontChoice = FontChoice.System,
    val sourceSizeSp: Int = 15,
    val translationSizeSp: Int = 17,
    val recognitionEngine: RecognitionEngine = RecognitionEngine.Nemotron,
    val translationSettings: TranslationSettings = TranslationSettings(),
    val entries: List<SessionEntry> = emptyList(),
    val message: String = "",
)
