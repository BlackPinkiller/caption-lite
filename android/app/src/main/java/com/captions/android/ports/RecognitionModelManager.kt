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
