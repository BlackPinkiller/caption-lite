package com.captions.android.core.recognition

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VadGateTest {
    @Test
    fun keepsTheSentenceOnsetWhenConfirmationLags() {
        val windowSize = 4
        val onsetWindow = 32
        val confirmWindow = 56
        val total = 64
        val samples = ShortArray(total * windowSize) { it.toShort() }

        val gate = VadGate(LaggingVad(confirmWindow), windowSize = windowSize)
        val emitted = gate.process(samples)
            .flatMap { it.samples.toList() }
            .toShortArray()

        val onset = onsetWindow * windowSize
        assertTrue("sentence onset was evicted", emitted[0].toInt() <= onset)
    }

    @Test
    fun reportsTheEndpointAtTheSpeechSilenceBoundaryBeforeTheNextOnset() {
        val states = listOf(true, true, true, false, false, false, true, true)
        val gate = VadGate(StateVad(states), windowSize = 4)
        val samples = ShortArray(8 * 4) { it.toShort() }

        val events = gate.process(samples)

        val endpointAt = events.indexOfFirst { it.vadEndpoint }
        val nextOnsetAt = events.indexOfFirst { event ->
            event.samples.any { sample -> sample.toInt() >= 6 * 4 }
        }
        assertEquals(3, endpointAt)
        assertTrue("endpoint fired after the next sentence onset", endpointAt < nextOnsetAt)
    }

    @Test
    fun carriesPartialWindowsAcrossProcessCalls() {
        val gate = VadGate(StateVad(listOf(true, false, true)), windowSize = 4)
        val first = ShortArray(5) { it.toShort() }
        val second = ShortArray(3) { (it + 5).toShort() }

        val delivered = gate.process(first).sumOf { it.samples.size } +
            gate.process(second).sumOf { it.samples.size }

        assertEquals(8, delivered)
    }

    private class LaggingVad(private val confirmIndex: Int) : SpeechActivityVad {
        private var index = -1
        private var detected = false

        override fun acceptWaveform(window: FloatArray) {
            index += 1
            detected = index >= confirmIndex
        }

        override fun isSpeechDetected(): Boolean = detected

        override fun drainCompletedSegments() = Unit

        override fun reset() {
            index = -1
            detected = false
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
