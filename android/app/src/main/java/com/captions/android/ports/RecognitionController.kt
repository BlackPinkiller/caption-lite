package com.captions.android.ports

interface RecognitionController {
    fun start()
    fun pause()
    fun setMicrophoneEnabled(enabled: Boolean)
}
