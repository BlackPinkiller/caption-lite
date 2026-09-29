package com.captions.android.core.session

/** Display preferences stay intact when translation is temporarily disabled. */
fun SessionUiState.effectiveDisplayMode(): DisplayMode =
    if (translationSettings.enabled) displayMode else DisplayMode.Source

fun SessionUiState.overlayEntry(): SessionEntry? = when (effectiveDisplayMode()) {
    // Keep the last readable translation until a newer one is ready. Choose a
    // whole entry so source and translation can never come from different cues.
    DisplayMode.Translation -> entries.lastOrNull { it.translation.isNotBlank() }
    DisplayMode.Source -> entries.lastOrNull { it.source.isNotBlank() }
    DisplayMode.Bilingual -> entries.lastOrNull { it.source.isNotBlank() || it.translation.isNotBlank() }
}
