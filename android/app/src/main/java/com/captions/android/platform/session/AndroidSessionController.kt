package com.captions.android.platform.session

import com.captions.android.ports.AudioInput
import com.captions.android.ports.RecognitionController
import com.captions.android.ui.session.SessionViewModel

class AndroidSessionController(
    private val audioInput: AudioInput,
    private val viewModel: SessionViewModel,
) : RecognitionController, AutoCloseable {
    override fun start() {
        if (!viewModel.state.value.microphoneEnabled) {
            viewModel.start()
            return
        }
        try {
            audioInput.start(
                onSamples = { _ -> },
                onError = {
                    viewModel.pause()
                    viewModel.showMessage(it)
                },
            )
            viewModel.start()
        } catch (error: IllegalStateException) {
            viewModel.pause()
            viewModel.showMessage(error.message ?: "无法启动麦克风")
        } catch (error: IllegalArgumentException) {
            viewModel.pause()
            viewModel.showMessage(error.message ?: "无法启动麦克风")
        }
    }

    override fun pause() {
        audioInput.stop()
        viewModel.pause()
    }

    override fun setMicrophoneEnabled(enabled: Boolean) {
        if (!enabled) {
            audioInput.stop()
        }
        viewModel.setMicrophoneEnabled(enabled)
        if (enabled && viewModel.state.value.running) {
            start()
        }
    }

    override fun close() {
        audioInput.close()
    }
}
