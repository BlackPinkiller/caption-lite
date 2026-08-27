package com.captions.android.platform.session

import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.recognition.RecognitionSegmenter
import com.captions.android.core.recognition.PunctuationMode
import com.captions.android.ports.AudioInput
import com.captions.android.ports.DirectRecognitionSession
import com.captions.android.ports.RecognitionController
import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.SampleRecognitionSession
import com.captions.android.ports.TranslationSession
import com.captions.android.ports.SessionStateController
import java.util.concurrent.atomic.AtomicBoolean

class AndroidSessionController(
    private val audioInput: AudioInput,
    private val viewModel: SessionStateController,
    private val recognitionSession: SampleRecognitionSession? = null,
    private val systemRecognitionSession: DirectRecognitionSession? = null,
    private val translationSession: TranslationSession? = null,
    private val segmenter: RecognitionSegmenter = RecognitionSegmenter(),
) : RecognitionController, AutoCloseable {
    private val startRequested = AtomicBoolean(false)
    private var cueId = 1L

    fun setPunctuationMode(mode: PunctuationMode) {
        segmenter.punctuationMode = mode
    }

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
        segmenter.reset()
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
        segmenter.reset()
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
        var active = segmenter.active
        if (update.text.isNotEmpty()) {
            val segmented = segmenter.update(update.text)
            segmented.commits.forEach { commitSource(it.text) }
            active = segmented.active
        }
        if (update.endpoint) {
            val flushed = segmenter.flush()
            flushed.commits.forEach { commitSource(it.text) }
        } else if (active.isNotBlank()) {
            publishActive(active)
        }
    }

    private fun publishActive(source: String) {
        viewModel.updateCurrent(cueId, source)
        val translationSettings = viewModel.state.value.translationSettings
        if (translationSettings.enabled) {
            translationSession?.preview(
                cueId = cueId,
                text = source,
                context = translationContext(cueId, translationSettings.contextSegments),
                settings = translationSettings,
                onResult = viewModel::updateTranslation,
            )
        }
    }

    private fun commitSource(source: String) {
        val committed = source.trim()
        if (committed.isEmpty()) return
        val currentCueId = cueId
        viewModel.updateCurrent(currentCueId, committed)
        viewModel.commitCurrent()
        requestFinalTranslation(
            currentCueId,
            committed,
            viewModel.state.value.translationSettings,
        )
        cueId += 1
    }

    private fun commitActiveCue() {
        val segmented = segmenter.flush(forced = true)
        val current = viewModel.state.value.entries.lastOrNull()?.takeIf { it.current }
        val source = segmented.commits.firstOrNull()?.text?.takeIf { it.isNotBlank() }
            ?: current?.source.orEmpty()
        if (source.isNotBlank()) commitSource(source)
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
        commitActiveCue()
        viewModel.pause()
        viewModel.showMessage(message)
    }

    override fun pause() {
        startRequested.set(false)
        audioInput.stop()
        recognitionSession?.stop()
        systemRecognitionSession?.stop()
        commitActiveCue()
        viewModel.pause()
    }

    override fun setMicrophoneEnabled(enabled: Boolean) {
        if (!enabled) {
            startRequested.set(false)
            audioInput.stop()
            recognitionSession?.stop()
            systemRecognitionSession?.stop()
            commitActiveCue()
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
