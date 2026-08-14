package com.captions.android.platform.recognition

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import com.captions.android.ports.DirectRecognitionSession
import com.captions.android.ports.RecognitionUpdate
import java.util.Locale

class AndroidSystemRecognitionSession(
    context: Context,
    private val language: () -> String,
) : DirectRecognitionSession {
    private val appContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    private var active = false
    private var runId = 0L
    private var restartAction: Runnable? = null
    private var onReady: () -> Unit = {}
    private var onUpdate: (RecognitionUpdate) -> Unit = {}
    private var onError: (String) -> Unit = {}

    override fun start(
        onReady: () -> Unit,
        onUpdate: (RecognitionUpdate) -> Unit,
        onError: (String) -> Unit,
    ) {
        runOnMain {
            if (active) return@runOnMain
            if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(appContext)) {
                onError("设备不支持本地系统识别")
                return@runOnMain
            }
            this.onReady = onReady
            this.onUpdate = onUpdate
            this.onError = onError
            active = true
            runId += 1
            val currentRun = runId
            releaseRecognizer()
            recognizer = SpeechRecognizer.createOnDeviceSpeechRecognizer(appContext).apply {
                setRecognitionListener(listener(currentRun))
            }
            listen(currentRun)
        }
    }

    private fun listen(currentRun: Long) {
        if (!isActive(currentRun)) return
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, recognitionLanguageTag(language()))
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            putExtra(
                RecognizerIntent.EXTRA_SEGMENTED_SESSION,
                RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS,
            )
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 800)
        }
        recognizer?.startListening(intent)
    }

    private fun restart(currentRun: Long, delayMillis: Long = RESTART_DELAY_MILLIS) {
        if (!isActive(currentRun)) return
        restartAction?.let(handler::removeCallbacks)
        restartAction = Runnable { listen(currentRun) }.also {
            handler.postDelayed(it, delayMillis)
        }
    }

    private fun listener(currentRun: Long) = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            if (isActive(currentRun)) onReady()
        }
        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit
        override fun onEndOfSpeech() = Unit

        override fun onError(error: Int) {
            if (!isActive(currentRun)) return
            when (error) {
                SpeechRecognizer.ERROR_NO_MATCH,
                SpeechRecognizer.ERROR_SPEECH_TIMEOUT,
                -> restart(currentRun)

                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> restart(currentRun, BUSY_RETRY_MILLIS)
                else -> {
                    active = false
                    runId += 1
                    releaseRecognizer()
                    onError(errorMessage(error))
                }
            }
        }

        override fun onResults(results: Bundle) {
            if (!isActive(currentRun)) return
            resultText(results)?.let { onUpdate(RecognitionUpdate(it, endpoint = true)) }
            restart(currentRun)
        }

        override fun onPartialResults(partialResults: Bundle) {
            if (!isActive(currentRun)) return
            resultText(partialResults)?.let { onUpdate(RecognitionUpdate(it, endpoint = false)) }
        }

        override fun onSegmentResults(segmentResults: Bundle) {
            if (!isActive(currentRun)) return
            resultText(segmentResults)?.let { onUpdate(RecognitionUpdate(it, endpoint = true)) }
        }

        override fun onEndOfSegmentedSession() = restart(currentRun)
        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    private fun resultText(results: Bundle): String? =
        results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull()
            ?.trim()
            ?.takeIf(String::isNotEmpty)

    override fun stop() {
        runOnMain {
            active = false
            runId += 1
            restartAction?.let(handler::removeCallbacks)
            restartAction = null
            releaseRecognizer()
        }
    }

    override fun close() {
        runOnMain {
            active = false
            runId += 1
            restartAction?.let(handler::removeCallbacks)
            restartAction = null
            releaseRecognizer()
        }
    }

    private fun releaseRecognizer() {
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
    }

    private fun isActive(currentRun: Long): Boolean = active && runId == currentRun

    private fun runOnMain(action: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) action() else handler.post(action)
    }

    private fun errorMessage(error: Int): String = when (error) {
        SpeechRecognizer.ERROR_AUDIO -> "系统识别无法使用麦克风"
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "系统识别缺少麦克风权限"
        SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED -> "系统识别不支持当前语言"
        SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> "当前语言尚未下载"
        SpeechRecognizer.ERROR_NETWORK,
        SpeechRecognizer.ERROR_NETWORK_TIMEOUT,
        -> "系统识别暂时不可用"

        else -> "系统识别失败"
    }

    private companion object {
        const val RESTART_DELAY_MILLIS = 150L
        const val BUSY_RETRY_MILLIS = 500L
    }
}

internal fun recognitionLanguageTag(language: String): String =
    Locale.forLanguageTag(language).takeIf { it.language.isNotBlank() }
        ?.toLanguageTag()
        ?: Locale.getDefault().toLanguageTag()
