package com.captions.android.core.recognition

import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.StreamingRecognizer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VadGatedStreamingRecognizerTest {
    @Test
    fun emptyVadEndpointDoesNotCreateAnEmptyCommit() {
        val inner = RecordingRecognizer() // the recognizer itself never reports an endpoint
        val gate = VadGate(
            StateVad(listOf(true, true, true, false, false, false, true)),
            windowSize = 4,
        )
        val wrapped = VadGatedStreamingRecognizer(inner, gate)

        val update = wrapped.accept(ShortArray(7 * 4) { it.toShort() })

        assertFalse(update.endpoint)
        assertEquals("", update.text)
    }

    @Test
    fun shortVadEndpointKeepsRecognitionOpenUntilTheMinimumIsReached() {
        val inner = RecordingRecognizer(text = "ok")
        val gate = VadGate(StateVad(listOf(true, false)), windowSize = 4)
        val wrapped = VadGatedStreamingRecognizer(inner, gate, minCommitChars = 4)

        val update = wrapped.accept(ShortArray(8) { it.toShort() })

        assertFalse(update.endpoint)
        assertEquals("ok", update.text)
        assertEquals(0, inner.resetCount)
    }

    @Test
    fun recognizerEndpointBypassesTheMinimum() {
        val inner = RecordingRecognizer(text = "ok", endpoint = true)
        val gate = VadGate(StateVad(listOf(true)), windowSize = 4)
        val wrapped = VadGatedStreamingRecognizer(inner, gate, minCommitChars = 4)

        val update = wrapped.accept(ShortArray(4) { it.toShort() })

        assertTrue(update.endpoint)
        assertEquals("ok", update.text)
    }

    @Test
    fun feedsTheNextUtteranceOnsetAfterAReset() {
        val inner = RecordingRecognizer(text = "recognized")
        val gate = VadGate(StateVad(listOf(true, false, true)), windowSize = 4)
        val wrapped = VadGatedStreamingRecognizer(inner, gate)

        wrapped.accept(ShortArray(5) { it.toShort() })
        wrapped.reset()
        val update = wrapped.accept(ShortArray(6) { (it + 8).toShort() })

        assertTrue(inner.received.any { chunk -> chunk.any { it.toInt() >= 8 } })
        assertEquals("recognized", update.text)
    }

    @Test
    fun keepsTheNextOnsetWhenItSharesAChunkWithTheEndpoint() {
        val inner = RecordingRecognizer(text = "recognized")
        val gate = VadGate(StateVad(listOf(true, false, true)), windowSize = 4)
        val wrapped = VadGatedStreamingRecognizer(inner, gate)

        val update = wrapped.accept(ShortArray(12) { it.toShort() })
        wrapped.reset()

        assertTrue(update.endpoint)
        assertTrue(inner.received.any { chunk -> chunk.any { it.toInt() >= 8 } })
    }

    @Test
    fun flushesTheRecognizerSoTheEndpointCommitKeepsTheSentenceTail() {
        val inner = TailLagRecognizer()
        val gate = VadGate(StateVad(listOf(true, false)), windowSize = 4)
        val wrapped = VadGatedStreamingRecognizer(inner, gate)
        val speech = shortArrayOf(1, 2, 3, 4, 0, 0, 0, 0)

        val update = wrapped.accept(speech)

        assertEquals("full sentence with tail", update.text)
        assertTrue(update.endpoint)
    }

    /**
     * Mimics the streaming model's chunk latency: the final tokens of a
     * sentence are only emitted after the recognizer receives a silent flush
     * that is longer than the VAD's trailing silence.
     */
    private class TailLagRecognizer : StreamingRecognizer {
        private var speechSeen = false

        override fun accept(samples: ShortArray): RecognitionUpdate {
            val hasSpeech = samples.any { it != 0.toShort() }
            if (hasSpeech) speechSeen = true
            val text = when {
                speechSeen && !hasSpeech && samples.size >= VAD_FLUSH_SAMPLES ->
                    "full sentence with tail"
                speechSeen -> "full sentence"
                else -> ""
            }
            return RecognitionUpdate(text = text, endpoint = false)
        }

        override fun reset() {
            speechSeen = false
        }

        override fun close() = Unit
    }

    private class RecordingRecognizer(
        private val text: String = "",
        private val endpoint: Boolean = false,
    ) : StreamingRecognizer {
        val received = mutableListOf<ShortArray>()
        var resetCount = 0

        override fun reset() {
            resetCount += 1
            received.clear()
        }

        override fun accept(samples: ShortArray): RecognitionUpdate {
            received += samples
            return RecognitionUpdate(text = text, endpoint = endpoint)
        }

        override fun close() = Unit
    }

    private class StateVad(private val states: List<Boolean>) : SpeechActivityVad {
        private var index = -1
        private var detected = false

        override fun acceptWaveform(window: FloatArray) {
            index += 1
            detected = index < states.size && states[index]
        }

        override fun isSpeechDetected(): Boolean = detected

        override fun drainCompletedSegments() = Unit

        override fun reset() {
            index = -1
            detected = false
        }

        override fun close() = Unit
    }
}
