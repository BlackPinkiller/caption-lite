package com.captions.android.platform.recognition

import android.content.res.AssetManager
import com.captions.android.core.recognition.SpeechActivityVad
import com.captions.android.core.recognition.VAD_WINDOW_SIZE
import com.k2fsa.sherpa.onnx.SileroVadModelConfig
import com.k2fsa.sherpa.onnx.TenVadModelConfig
import com.k2fsa.sherpa.onnx.Vad
import com.k2fsa.sherpa.onnx.VadModelConfig

/**
 * Adapts sherpa-onnx's native VAD to [SpeechActivityVad]. The model is bundled in
 * the app assets and loaded through [AssetManager].
 */
class SherpaSpeechActivityVad(
    assetManager: AssetManager,
    private val vad: Vad = Vad(
        assetManager,
        VadModelConfig(
            sileroVadModelConfig = SileroVadModelConfig(
                model = "silero_vad.int8.onnx",
                threshold = 0.25f,
                minSilenceDuration = 0.4f,
                minSpeechDuration = 0.25f,
                windowSize = VAD_WINDOW_SIZE,
                maxSpeechDuration = 20.0f,
            ),
            tenVadModelConfig = TenVadModelConfig(),
            sampleRate = 16_000,
            numThreads = 1,
            provider = "cpu",
            debug = false,
        ),
    ),
) : SpeechActivityVad {
    override fun acceptWaveform(window: FloatArray) = vad.acceptWaveform(window)

    override fun isSpeechDetected(): Boolean = vad.isSpeechDetected()

    override fun drainCompletedSegments() {
        while (!vad.empty()) vad.pop()
    }

    override fun reset() {
        vad.clear()
        vad.reset()
    }

    override fun close() {
        vad.release()
    }
}
