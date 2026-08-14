package com.captions.android.core.recognition

import android.util.Log

const val VAD_WINDOW_SIZE = 512
const val VAD_PRE_ROLL_WINDOWS = 48

/**
 * Silence fed to the recognizer at a VAD endpoint so the streaming model
 * emits the final tokens of the sentence (the model's chunk latency is
 * ~560ms, longer than the 400ms VAD trailing silence).
 */
const val VAD_FLUSH_SAMPLES = 9600

/**
 * Voice-activity detector abstraction used by [VadGate]. The real implementation
 * wraps sherpa-onnx's native [com.k2fsa.sherpa.onnx.Vad]; tests inject fakes.
 */
interface SpeechActivityVad {
    fun acceptWaveform(window: FloatArray)
    fun isSpeechDetected(): Boolean
    fun drainCompletedSegments()
    fun reset()
    fun close()
}

data class GatedAudio(val samples: ShortArray, val vadEndpoint: Boolean)

/**
 * Mirrors the desktop `VadSpeechGate`: gates non-speech audio while preserving
 * the sentence onset. Only windows around confirmed speech are forwarded to the
 * recognizer, but the pre-roll is large enough to cover the VAD confirmation
 * latency so the first words of the next sentence are never evicted. The
 * pre-roll only accumulates while speech is inactive and is cleared after each
 * detection, so it never re-feeds the previous sentence's tail.
 */
class VadGate(
    private val vad: SpeechActivityVad,
    private val windowSize: Int = VAD_WINDOW_SIZE,
    private val preRollWindows: Int = VAD_PRE_ROLL_WINDOWS,
) {
    private val preRoll = ArrayDeque<ShortArray>()
    private var pending = ShortArray(0)
    private var speechActive = false

    fun reset() {
        vad.reset()
        pending = ShortArray(0)
        preRoll.clear()
        speechActive = false
    }

    fun close() {
        vad.close()
    }

    fun process(samples: ShortArray): List<GatedAudio> {
        val combined = if (pending.isEmpty()) samples else pending + samples
        val events = mutableListOf<GatedAudio>()
        var offset = 0
        while (offset + windowSize <= combined.size) {
            val window = combined.copyOfRange(offset, offset + windowSize)
            offset += windowSize
            val wasActive = speechActive
            if (!wasActive) {
                if (preRoll.size == preRollWindows) preRoll.removeFirst()
                preRoll.addLast(window)
            }
            vad.acceptWaveform(toFloat(window))
            val detected = vad.isSpeechDetected()
            when {
                wasActive && !detected -> {
                    events += GatedAudio(window, vadEndpoint = true)
                    Log.d(LOG_TAG, "endpoint at window $offset")
                }
                wasActive -> events += GatedAudio(window, vadEndpoint = false)
                detected -> {
                    events += GatedAudio(concat(preRoll), vadEndpoint = false)
                    preRoll.clear()
                }
            }
            speechActive = detected
            vad.drainCompletedSegments()
        }
        pending = combined.copyOfRange(offset, combined.size)
        return events
    }

    private fun toFloat(samples: ShortArray): FloatArray =
        FloatArray(samples.size) { samples[it] / 32768f }

    private fun concat(queued: ArrayDeque<ShortArray>): ShortArray {
        var total = 0
        for (chunk in queued) total += chunk.size
        val result = ShortArray(total)
        var offset = 0
        for (chunk in queued) {
            for (index in chunk.indices) result[offset + index] = chunk[index]
            offset += chunk.size
        }
        return result
    }

    private companion object {
        const val LOG_TAG = "CaptionsVad"
    }
}
