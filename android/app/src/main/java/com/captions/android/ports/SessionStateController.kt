package com.captions.android.ports

import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.OverlayPosition
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.SessionUiState
import com.captions.android.core.session.TranslationSettings
import kotlinx.coroutines.flow.StateFlow

interface SessionStateController {
    val state: StateFlow<SessionUiState>

    fun start()
    fun beginStarting(message: String)
    fun pause()
    fun setMicrophoneEnabled(enabled: Boolean)
    fun setDisplayMode(mode: DisplayMode)
    fun setFontChoice(choice: FontChoice)
    fun setSourceSize(sizeSp: Int)
    fun setTranslationSize(sizeSp: Int)
    fun setOverlayEnabled(enabled: Boolean)
    fun setOverlayBackgroundEnabled(enabled: Boolean)
    fun setOverlayPosition(position: OverlayPosition)
    fun setRecognitionEngine(engine: RecognitionEngine)
    fun setTranslationSettings(settings: TranslationSettings)
    fun showMessage(message: String)
    fun updateCurrent(cueId: Long, source: String, translation: String? = null)
    fun commitCurrent()
    fun updateTranslation(cueId: Long, translation: String)
}
