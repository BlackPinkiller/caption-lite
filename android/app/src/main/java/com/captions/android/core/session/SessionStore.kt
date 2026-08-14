package com.captions.android.core.session

import com.captions.android.ports.SessionStateController
import com.captions.android.ports.SettingsStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class SessionStore(
    private val settingsStore: SettingsStore,
) : SessionStateController {
    private val timeline = SessionTimeline()
    private val initialRecognitionEngine = settingsStore.loadRecognitionEngine()
    private val initialTranslationSettings = settingsStore.loadTranslation()
        .forRecognitionEngine(initialRecognitionEngine)
    private val mutableState = MutableStateFlow(
        settingsStore.loadAppearance().let {
            SessionUiState(
                displayMode = it.displayMode,
                fontChoice = it.fontChoice,
                sourceSizeSp = it.sourceSizeSp,
                translationSizeSp = it.translationSizeSp,
                overlayEnabled = it.overlayEnabled,
                overlayBackgroundEnabled = it.overlayBackgroundEnabled,
                overlayPosition = it.overlayPosition,
                recognitionEngine = initialRecognitionEngine,
                translationSettings = initialTranslationSettings,
            )
        },
    )

    override val state: StateFlow<SessionUiState> = mutableState.asStateFlow()

    override fun start() {
        if (!mutableState.value.microphoneEnabled) {
            showMessage("麦克风已关闭")
            return
        }
        mutableState.value = mutableState.value.copy(running = true, starting = false, message = "")
    }

    override fun beginStarting(message: String) {
        mutableState.value = mutableState.value.copy(
            running = false,
            starting = true,
            message = message.trim(),
        )
    }

    override fun pause() {
        mutableState.value = mutableState.value.copy(running = false, starting = false)
    }

    override fun setMicrophoneEnabled(enabled: Boolean) {
        mutableState.value = mutableState.value.copy(
            microphoneEnabled = enabled,
            starting = if (enabled) mutableState.value.starting else false,
            message = "",
        )
    }

    override fun setDisplayMode(mode: DisplayMode) {
        mutableState.value = mutableState.value.copy(displayMode = mode)
        saveAppearance()
    }

    override fun setFontChoice(choice: FontChoice) {
        mutableState.value = mutableState.value.copy(fontChoice = choice)
        saveAppearance()
    }

    override fun setSourceSize(sizeSp: Int) {
        mutableState.value = mutableState.value.copy(sourceSizeSp = sizeSp.coerceIn(12, 40))
        saveAppearance()
    }

    override fun setTranslationSize(sizeSp: Int) {
        mutableState.value = mutableState.value.copy(translationSizeSp = sizeSp.coerceIn(12, 40))
        saveAppearance()
    }

    override fun setOverlayEnabled(enabled: Boolean) {
        mutableState.value = mutableState.value.copy(overlayEnabled = enabled)
        saveAppearance()
    }

    override fun setOverlayBackgroundEnabled(enabled: Boolean) {
        mutableState.value = mutableState.value.copy(overlayBackgroundEnabled = enabled)
        saveAppearance()
    }

    override fun setOverlayPosition(position: OverlayPosition) {
        mutableState.value = mutableState.value.copy(overlayPosition = position)
        saveAppearance()
    }

    override fun setRecognitionEngine(engine: RecognitionEngine) {
        val translationSettings = mutableState.value.translationSettings.forRecognitionEngine(engine)
        mutableState.value = mutableState.value.copy(
            recognitionEngine = engine,
            translationSettings = translationSettings,
            message = "",
        )
        settingsStore.saveRecognitionEngine(engine)
        settingsStore.saveTranslation(translationSettings)
    }

    override fun setTranslationSettings(settings: TranslationSettings) {
        val normalized = settings.forRecognitionEngine(mutableState.value.recognitionEngine)
        mutableState.value = mutableState.value.copy(
            translationSettings = normalized,
            message = "",
        )
        settingsStore.saveTranslation(normalized)
    }

    override fun showMessage(message: String) {
        mutableState.value = mutableState.value.copy(message = message.trim())
    }

    override fun updateCurrent(cueId: Long, source: String, translation: String?) {
        timeline.updateCurrent(cueId, source, translation)
        publishTimeline()
    }

    override fun commitCurrent() {
        timeline.commitCurrent()
        publishTimeline()
    }

    override fun updateTranslation(cueId: Long, translation: String) {
        if (timeline.updateTranslation(cueId, translation)) publishTimeline()
    }

    private fun publishTimeline() {
        mutableState.value = mutableState.value.copy(entries = timeline.entries)
    }

    private fun saveAppearance() {
        val current = mutableState.value
        settingsStore.saveAppearance(
            AppearanceSettings(
                displayMode = current.displayMode,
                fontChoice = current.fontChoice,
                sourceSizeSp = current.sourceSizeSp,
                translationSizeSp = current.translationSizeSp,
                overlayEnabled = current.overlayEnabled,
                overlayBackgroundEnabled = current.overlayBackgroundEnabled,
                overlayPosition = current.overlayPosition,
            ),
        )
    }
}
