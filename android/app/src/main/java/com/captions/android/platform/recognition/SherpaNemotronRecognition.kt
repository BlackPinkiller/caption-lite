package com.captions.android.platform.recognition

import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.StreamingRecognizer
import com.captions.android.ports.StreamingRecognizerFactory
import com.k2fsa.sherpa.onnx.EndpointConfig
import com.k2fsa.sherpa.onnx.EndpointRule
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineRecognizer
import com.k2fsa.sherpa.onnx.OnlineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineStream
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig
import java.io.File

class SherpaNemotronRecognitionFactory(
    private val modelDirectory: () -> File,
) : StreamingRecognizerFactory {
    override fun create(): StreamingRecognizer {
        val directory = modelDirectory()
        val files = MODEL_FILES.associateWith { File(directory, it) }
        require(files.values.all(File::isFile)) { "请先下载 Nemotron 模型" }

        val modelConfig = OnlineModelConfig(
            transducer = OnlineTransducerModelConfig(
                encoder = files.getValue("encoder.int8.onnx").absolutePath,
                decoder = files.getValue("decoder.int8.onnx").absolutePath,
                joiner = files.getValue("joiner.int8.onnx").absolutePath,
            ),
            tokens = files.getValue("tokens.txt").absolutePath,
            numThreads = THREAD_COUNT,
            provider = "cpu",
        )
        val config = OnlineRecognizerConfig(
            featConfig = FeatureConfig(
                sampleRate = SAMPLE_RATE,
                featureDim = FEATURE_DIM,
                dither = 0f,
            ),
            modelConfig = modelConfig,
            endpointConfig = EndpointConfig(
                rule1 = EndpointRule(false, 2.4f, 0f),
                rule2 = EndpointRule(true, 0.8f, 0f),
                rule3 = EndpointRule(false, 0f, 20f),
            ),
            enableEndpoint = true,
            decodingMethod = "greedy_search",
        )
        return SherpaNemotronRecognition(OnlineRecognizer(assetManager = null, config = config))
    }

    private companion object {
        const val SAMPLE_RATE = 16_000
        const val FEATURE_DIM = 80
        const val THREAD_COUNT = 4
        val MODEL_FILES = listOf(
            "encoder.int8.onnx",
            "decoder.int8.onnx",
            "joiner.int8.onnx",
            "tokens.txt",
        )
    }
}

private class SherpaNemotronRecognition(
    private val recognizer: OnlineRecognizer,
) : StreamingRecognizer {
    private var stream: OnlineStream = recognizer.createStream()

    override fun reset() {
        recognizer.reset(stream)
    }

    override fun accept(samples: ShortArray): RecognitionUpdate {
        val normalized = FloatArray(samples.size) { samples[it] / 32768f }
        stream.acceptWaveform(normalized, sampleRate = SAMPLE_RATE)
        while (recognizer.isReady(stream)) recognizer.decode(stream)
        return RecognitionUpdate(
            text = recognizer.getResult(stream).text.trim(),
            endpoint = recognizer.isEndpoint(stream),
        )
    }

    override fun close() {
        stream.release()
        recognizer.release()
    }

    private companion object {
        const val SAMPLE_RATE = 16_000
    }
}
