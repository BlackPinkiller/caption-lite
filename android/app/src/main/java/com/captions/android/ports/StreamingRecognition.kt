package com.captions.android.ports

data class RecognitionUpdate(
    val text: String,
    val endpoint: Boolean,
)

interface StreamingRecognizer : AutoCloseable {
    fun reset()
    fun accept(samples: ShortArray): RecognitionUpdate
}

fun interface StreamingRecognizerFactory {
    fun create(): StreamingRecognizer
}

interface SampleRecognitionSession : AutoCloseable {
    fun start(
        onReady: () -> Unit,
        onUpdate: (RecognitionUpdate) -> Unit,
        onError: (String) -> Unit,
    )

    fun accept(samples: ShortArray): Boolean
    fun stop()
}

interface DirectRecognitionSession : AutoCloseable {
    fun start(
        onReady: () -> Unit,
        onUpdate: (RecognitionUpdate) -> Unit,
        onError: (String) -> Unit,
    )

    fun stop()
}
