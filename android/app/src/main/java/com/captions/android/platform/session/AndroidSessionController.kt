package com.captions.android.platform.session

import com.captions.android.core.session.RecognitionEngine
import com.captions.android.ports.AudioInput
import com.captions.android.ports.DirectRecognitionSession
import com.captions.android.ports.RecognitionController
import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.SampleRecognitionSession
import com.captions.android.ui.session.SessionViewModel
import java.util.concurrent.atomic.AtomicBoolean

class AndroidSessionController(
    private val audioInput: AudioInput,
    private val viewModel: SessionViewModel,
    private val recognitionSession: SampleRecognitionSession? = null,
    private val systemRecognitionSession: DirectRecognitionSession? = null,
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
        viewModel.showMessage("正在加载模型")
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
        viewModel.showMessage("正在启动系统识别")
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
        if (update.endpoint) {
            viewModel.commitCurrent()
            cueId += 1
        }
    }

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
        if (viewModel.state.value.entries.lastOrNull()?.current == true) {
            viewModel.commitCurrent()
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
        audioInput.close()
    }
}
