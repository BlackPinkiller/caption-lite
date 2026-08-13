package com.captions.android.ui.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.captions.android.core.session.AppearanceSettings
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.SessionTimeline
import com.captions.android.core.session.SessionUiState
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.SettingsStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class SessionViewModel(private val settingsStore: SettingsStore) : ViewModel() {
    private val timeline = SessionTimeline()
    private val mutableState = MutableStateFlow(
        settingsStore.loadAppearance().let {
            SessionUiState(
                displayMode = it.displayMode,
                fontChoice = it.fontChoice,
                sourceSizeSp = it.sourceSizeSp,
                translationSizeSp = it.translationSizeSp,
                recognitionEngine = settingsStore.loadRecognitionEngine(),
                translationSettings = settingsStore.loadTranslation(),
            )
        },
    )

    val state: StateFlow<SessionUiState> = mutableState.asStateFlow()

    fun start() {
        if (!mutableState.value.microphoneEnabled) {
            showMessage("麦克风已关闭")
            return
        }
        mutableState.value = mutableState.value.copy(running = true, message = "")
    }

    fun pause() {
        mutableState.value = mutableState.value.copy(running = false)
    }

    fun setMicrophoneEnabled(enabled: Boolean) {
        mutableState.value = mutableState.value.copy(
            microphoneEnabled = enabled,
            message = "",
        )
    }

    fun setDisplayMode(mode: DisplayMode) {
        mutableState.value = mutableState.value.copy(displayMode = mode)
        saveAppearance()
    }

    fun setFontChoice(choice: FontChoice) {
        mutableState.value = mutableState.value.copy(fontChoice = choice)
        saveAppearance()
    }

    fun setSourceSize(sizeSp: Int) {
        mutableState.value = mutableState.value.copy(sourceSizeSp = sizeSp.coerceIn(12, 40))
        saveAppearance()
    }

    fun setTranslationSize(sizeSp: Int) {
        mutableState.value = mutableState.value.copy(translationSizeSp = sizeSp.coerceIn(12, 40))
        saveAppearance()
    }

    fun setRecognitionEngine(engine: RecognitionEngine) {
        mutableState.value = mutableState.value.copy(recognitionEngine = engine, message = "")
        settingsStore.saveRecognitionEngine(engine)
    }

    fun setTranslationSettings(settings: TranslationSettings) {
        mutableState.value = mutableState.value.copy(translationSettings = settings, message = "")
        settingsStore.saveTranslation(settings)
    }

    fun showMessage(message: String) {
        mutableState.value = mutableState.value.copy(message = message.trim())
    }

    fun updateCurrent(cueId: Long, source: String, translation: String = "") {
        timeline.updateCurrent(cueId, source, translation)
        publishTimeline()
    }

    fun commitCurrent() {
        timeline.commitCurrent()
        publishTimeline()
    }

    fun updateTranslation(cueId: Long, translation: String) {
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
            ),
        )
    }

    class Factory(private val settingsStore: SettingsStore) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(SessionViewModel::class.java))
            return SessionViewModel(settingsStore) as T
        }
    }
}
