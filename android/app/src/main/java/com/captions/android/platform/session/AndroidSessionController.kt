package com.captions.android.platform.session

import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.AudioInput
import com.captions.android.ports.DirectRecognitionSession
import com.captions.android.ports.RecognitionController
import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.SampleRecognitionSession
import com.captions.android.ports.TranslationSession
import com.captions.android.ui.session.SessionViewModel
import java.util.concurrent.atomic.AtomicBoolean

class AndroidSessionController(
    private val audioInput: AudioInput,
    private val viewModel: SessionViewModel,
    private val recognitionSession: SampleRecognitionSession? = null,
    private val systemRecognitionSession: DirectRecognitionSession? = null,
    private val translationSession: TranslationSession? = null,
) : RecognitionController, AutoCloseable {
    private val startRequested = AtomicBoolean(false)
    private var cueId = 1L

    override fun start() {
        if (!viewModel.state.value.microphoneEnabled) {
            viewModel.start()
            return
        }
        when (viewModel.state.value.recognitionEngine) {
            RecognitionEngine.Nemotron -> {
                if (recognitionSession != null) {
                    startRecognition()
                } else {
                    startAudioCapture()
                }
            }
            RecognitionEngine.AndroidSystem -> startSystemRecognition()
        }
    }

    private fun startRecognition() {
        if (!startRequested.compareAndSet(false, true)) return
        viewModel.beginStarting("正在加载模型")
        recognitionSession?.start(
            onReady = {
                if (startRequested.get()) startAudioCapture()
            },
            onUpdate = ::onRecognitionUpdate,
            onError = ::onRecognitionError,
        )
    }

    private fun startSystemRecognition() {
        val session = systemRecognitionSession
        if (session == null) {
            viewModel.showMessage("系统识别不可用")
            return
        }
        if (!startRequested.compareAndSet(false, true)) return
        viewModel.beginStarting("正在启动系统识别")
        session.start(
            onReady = {
                if (startRequested.get()) viewModel.start()
            },
            onUpdate = ::onRecognitionUpdate,
            onError = ::onRecognitionError,
        )
    }

    private fun startAudioCapture() {
        if (recognitionSession != null && !startRequested.get()) return
        try {
            audioInput.start(
                onSamples = { samples ->
                    if (recognitionSession != null && !recognitionSession.accept(samples)) {
                        onRecognitionError("设备无法及时处理音频")
                    }
                },
                onError = ::onRecognitionError,
            )
            viewModel.start()
        } catch (error: IllegalStateException) {
            onRecognitionError(error.message ?: "无法启动麦克风")
        } catch (error: IllegalArgumentException) {
            onRecognitionError(error.message ?: "无法启动麦克风")
        }
    }

    private fun onRecognitionUpdate(update: RecognitionUpdate) {
        if (update.text.isNotEmpty()) {
            viewModel.updateCurrent(cueId, update.text)
        }
        val currentCueId = cueId
        val source = viewModel.state.value.entries
            .lastOrNull { it.cueId == currentCueId }
            ?.source
            .orEmpty()
        val translationSettings = viewModel.state.value.translationSettings
        if (update.endpoint) {
            viewModel.commitCurrent()
            requestFinalTranslation(currentCueId, source, translationSettings)
            cueId += 1
        } else if (translationSettings.enabled && source.isNotBlank()) {
            translationSession?.preview(
                cueId = currentCueId,
                text = source,
                context = translationContext(currentCueId, translationSettings.contextSegments),
                settings = translationSettings,
                onResult = viewModel::updateTranslation,
            )
        }
    }

    private fun requestFinalTranslation(
        currentCueId: Long,
        source: String,
        settings: TranslationSettings,
    ) {
        if (!settings.enabled || source.isBlank()) return
        val accepted = translationSession?.commit(
            cueId = currentCueId,
            text = source,
            context = translationContext(currentCueId, settings.contextSegments),
            settings = settings,
            onResult = viewModel::updateTranslation,
            onError = viewModel::showMessage,
        ) ?: false
        if (!accepted && translationSession != null) {
            viewModel.showMessage("翻译任务过多，请稍后")
        }
    }

    private fun translationContext(currentCueId: Long, limit: Int): List<String> =
        viewModel.state.value.entries
            .asSequence()
            .filter { it.cueId != currentCueId && it.source.isNotBlank() }
            .map { it.source }
            .toList()
            .takeLast(limit)

    private fun onRecognitionError(message: String) {
        startRequested.set(false)
        recognitionSession?.stop()
        systemRecognitionSession?.stop()
        audioInput.stop()
        viewModel.pause()
        viewModel.showMessage(message)
    }

    override fun pause() {
        startRequested.set(false)
        audioInput.stop()
        recognitionSession?.stop()
        systemRecognitionSession?.stop()
        val current = viewModel.state.value.entries.lastOrNull()?.takeIf { it.current }
        if (current != null) {
            viewModel.commitCurrent()
            requestFinalTranslation(
                current.cueId,
                current.source,
                viewModel.state.value.translationSettings,
            )
            cueId += 1
        }
        viewModel.pause()
    }

    override fun setMicrophoneEnabled(enabled: Boolean) {
        if (!enabled) {
            startRequested.set(false)
            audioInput.stop()
            recognitionSession?.stop()
            systemRecognitionSession?.stop()
        }
        viewModel.setMicrophoneEnabled(enabled)
        if (enabled && viewModel.state.value.running) {
            start()
        }
    }

    override fun close() {
        startRequested.set(false)
        recognitionSession?.close()
        systemRecognitionSession?.close()
        translationSession?.close()
        audioInput.close()
    }
}
