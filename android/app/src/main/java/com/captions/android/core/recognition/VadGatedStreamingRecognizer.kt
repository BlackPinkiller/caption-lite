package com.captions.android.core.recognition

import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.StreamingRecognizer

/**
 * Wraps a streaming recognizer with a [VadGate] so the recognizer only receives
 * audio around confirmed speech. A VAD endpoint commits only after the minimum
 * text floor, while an explicit recognizer endpoint always commits.
 */
class VadGatedStreamingRecognizer(
    private val recognizer: StreamingRecognizer,
    private val gate: VadGate,
    private val minCommitChars: Int = 4,
) : StreamingRecognizer {
    private var endpointResetPending = false

    override fun reset() {
        // QueuedRecognitionSession resets after every surfaced endpoint. The
        // inner recognizer was already reset at the exact event boundary, so
        // keep any later onset that VadGate found in the same audio chunk.
        if (endpointResetPending) {
            endpointResetPending = false
            return
        }
        gate.reset()
        recognizer.reset()
    }

    override fun accept(samples: ShortArray): RecognitionUpdate {
        var text = ""
        var endpoint = false
        for (audio in gate.process(samples)) {
            val update = recognizer.accept(audio.samples)
            var currentText = update.text.ifEmpty { text }
            var asrEndpoint = update.endpoint
            if (audio.vadEndpoint) {
                val flushed = recognizer.accept(ShortArray(VAD_FLUSH_SAMPLES))
                if (flushed.text.isNotEmpty()) currentText = flushed.text
                asrEndpoint = asrEndpoint || flushed.endpoint
            }
            if (
                !endpoint &&
                SegmentationRules.shouldCommitEndpoint(
                    text = currentText,
                    vadEndpoint = audio.vadEndpoint,
                    asrEndpoint = asrEndpoint,
                    minChars = minCommitChars,
                )
            ) {
                text = currentText
                endpoint = true
                recognizer.reset()
                endpointResetPending = true
            } else if (!endpoint) {
                text = currentText
                if (audio.vadEndpoint && currentText.isBlank()) recognizer.reset()
            }
        }
        return RecognitionUpdate(text = text, endpoint = endpoint)
    }

    override fun close() {
        gate.close()
        recognizer.close()
    }
}
