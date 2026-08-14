package com.captions.android.ports

import kotlinx.coroutines.flow.StateFlow

enum class ModelPhase {
    Missing,
    Downloading,
    Preparing,
    Ready,
    Error,
}

data class ModelState(
    val phase: ModelPhase,
    val progressPercent: Int = 0,
    val detail: String = "",
)

interface RecognitionModelManager : AutoCloseable {
    val state: StateFlow<ModelState>

    fun refresh()
    fun download()
}

interface RecognitionLanguageModelManager : AutoCloseable {
    val state: StateFlow<ModelState>

    fun configure(language: String)
    fun refresh()
    fun download()
    fun isReady(language: String): Boolean
    fun installedLanguageTag(language: String): String?
}
