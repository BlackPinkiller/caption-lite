package com.captions.android.core.session

import com.captions.android.ports.SessionStateController
import com.captions.android.ports.SettingsStore
import com.captions.android.core.recognition.PunctuationMode
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
                nemotronModel = settingsStore.loadNemotronModel(),
                punctuationMode = settingsStore.loadPunctuationMode(),
                translationSettings = initialTranslationSettings,
            )
        },
    )

    override val state: StateFlow<SessionUiState> = mutableState.asStateFlow()

    // Recognition, preview/final translation, and UI settings arrive on
    // different threads. Mutate the timeline and publish its snapshot together.
    @Synchronized
    override fun start() {
        if (!mutableState.value.microphoneEnabled) {
            showMessage("麦克风已关闭")
            return
        }
        mutableState.value = mutableState.value.copy(running = true, starting = false, message = "")
    }

    @Synchronized
    override fun beginStarting(message: String) {
        mutableState.value = mutableState.value.copy(
            running = false,
            starting = true,
            message = message.trim(),
        )
    }

    @Synchronized
    override fun pause() {
        mutableState.value = mutableState.value.copy(running = false, starting = false)
    }

    @Synchronized
    override fun setMicrophoneEnabled(enabled: Boolean) {
        mutableState.value = mutableState.value.copy(
            microphoneEnabled = enabled,
            starting = if (enabled) mutableState.value.starting else false,
            message = "",
        )
    }

    @Synchronized
    override fun setDisplayMode(mode: DisplayMode) {
        mutableState.value = mutableState.value.copy(displayMode = mode)
        saveAppearance()
    }

    @Synchronized
    override fun setFontChoice(choice: FontChoice) {
        mutableState.value = mutableState.value.copy(fontChoice = choice)
        saveAppearance()
    }

    @Synchronized
    override fun setSourceSize(sizeSp: Int) {
        mutableState.value = mutableState.value.copy(sourceSizeSp = sizeSp.coerceIn(12, 40))
        saveAppearance()
    }

    @Synchronized
    override fun setTranslationSize(sizeSp: Int) {
        mutableState.value = mutableState.value.copy(translationSizeSp = sizeSp.coerceIn(12, 40))
        saveAppearance()
    }

    @Synchronized
    override fun setOverlayEnabled(enabled: Boolean) {
        mutableState.value = mutableState.value.copy(overlayEnabled = enabled)
        saveAppearance()
    }

    @Synchronized
    override fun setOverlayBackgroundEnabled(enabled: Boolean) {
        mutableState.value = mutableState.value.copy(overlayBackgroundEnabled = enabled)
        saveAppearance()
    }

    @Synchronized
    override fun setOverlayPosition(position: OverlayPosition) {
        mutableState.value = mutableState.value.copy(overlayPosition = position)
        saveAppearance()
    }

    @Synchronized
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

    @Synchronized
    override fun setNemotronModel(model: NemotronModel) {
        mutableState.value = mutableState.value.copy(nemotronModel = model, message = "")
        settingsStore.saveNemotronModel(model)
    }

    @Synchronized
    override fun setPunctuationMode(mode: PunctuationMode) {
        mutableState.value = mutableState.value.copy(
            punctuationMode = mode,
            message = "",
        )
        settingsStore.savePunctuationMode(mode)
    }

    @Synchronized
    override fun setTranslationSettings(settings: TranslationSettings) {
        val normalized = settings.forRecognitionEngine(mutableState.value.recognitionEngine)
        mutableState.value = mutableState.value.copy(
            translationSettings = normalized,
            message = "",
        )
        settingsStore.saveTranslation(normalized)
    }

    @Synchronized
    override fun showMessage(message: String) {
        mutableState.value = mutableState.value.copy(message = message.trim())
    }

    @Synchronized
    override fun updateCurrent(cueId: Long, source: String, translation: String?) {
        timeline.updateCurrent(cueId, source, translation)
        publishTimeline()
    }

    @Synchronized
    override fun commitCurrent() {
        timeline.commitCurrent()
        publishTimeline()
    }

    @Synchronized
    override fun updateTranslation(cueId: Long, translation: String, source: String?) {
        if (timeline.updateTranslation(cueId, translation, source)) publishTimeline()
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
