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
    val entries: List<SessionEntry> = emptyList(),
    val message: String = "",
)
