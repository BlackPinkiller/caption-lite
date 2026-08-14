package com.captions.android.core.recognition

import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.StreamingRecognizer

/**
 * Wraps a streaming recognizer with a [VadGate] so the recognizer only receives
 * audio around confirmed speech and sentence boundaries come from the VAD
 * (fast, precise) instead of the recognizer's own endpoint detection, which
 * fires late enough to swallow the start of the next sentence.
 */
class VadGatedStreamingRecognizer(
    private val recognizer: StreamingRecognizer,
    private val gate: VadGate,
) : StreamingRecognizer {
    override fun reset() {
        gate.reset()
        recognizer.reset()
    }

    override fun accept(samples: ShortArray): RecognitionUpdate {
        var text = ""
        var endpoint = false
        for (audio in gate.process(samples)) {
            val update = recognizer.accept(audio.samples)
            if (update.text.isNotEmpty()) text = update.text
            if (audio.vadEndpoint) {
                val flushed = recognizer.accept(ShortArray(VAD_FLUSH_SAMPLES))
                if (flushed.text.isNotEmpty()) text = flushed.text
                endpoint = true
            }
        }
        return RecognitionUpdate(text = text, endpoint = endpoint)
    }

    override fun close() {
        gate.close()
        recognizer.close()
    }
}
