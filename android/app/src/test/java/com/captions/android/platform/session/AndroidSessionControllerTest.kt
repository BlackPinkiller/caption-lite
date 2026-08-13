package com.captions.android.platform.session

import com.captions.android.core.session.AppearanceSettings
import com.captions.android.ports.AudioInput
import com.captions.android.ports.SettingsStore
import com.captions.android.ui.session.SessionViewModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidSessionControllerTest {
    @Test
    fun microphoneCanPauseAndResumeInsideARunningSession() {
        val audio = FakeAudioInput()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(audio, viewModel)

        controller.start()
        assertTrue(viewModel.state.value.running)
        assertEquals(1, audio.startCount)

        controller.setMicrophoneEnabled(false)
        assertTrue(viewModel.state.value.running)
        assertFalse(viewModel.state.value.microphoneEnabled)
        assertEquals(1, audio.stopCount)

        controller.setMicrophoneEnabled(true)
        assertTrue(viewModel.state.value.microphoneEnabled)
        assertEquals(2, audio.startCount)
    }

    @Test
    fun captureErrorStopsTheSessionAndReportsOneUsefulMessage() {
        val audio = FakeAudioInput()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(audio, viewModel)
        controller.start()

        audio.fail("麦克风读取失败")

        assertFalse(viewModel.state.value.running)
        assertEquals("麦克风读取失败", viewModel.state.value.message)
    }

    @Test
    fun disabledMicrophoneNeverStartsAudioCapture() {
        val audio = FakeAudioInput()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(audio, viewModel)

        controller.setMicrophoneEnabled(false)
        controller.start()

        assertFalse(viewModel.state.value.running)
        assertEquals(0, audio.startCount)
        assertEquals("麦克风已关闭", viewModel.state.value.message)
    }

    private class FakeAudioInput : AudioInput {
        override var running = false
        var startCount = 0
        var stopCount = 0
        private var errorCallback: (String) -> Unit = {}

        override fun start(onSamples: (ShortArray) -> Unit, onError: (String) -> Unit) {
            running = true
            startCount += 1
            errorCallback = onError
        }

        override fun stop() {
            running = false
            stopCount += 1
        }

        fun fail(message: String) = errorCallback(message)
    }

    private class MemorySettingsStore : SettingsStore {
        private var settings = AppearanceSettings()

        override fun loadAppearance(): AppearanceSettings = settings

        override fun saveAppearance(settings: AppearanceSettings) {
            this.settings = settings
        }
    }
}
