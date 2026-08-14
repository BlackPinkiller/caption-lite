package com.captions.android.platform.session

import com.captions.android.core.session.AppearanceSettings
import com.captions.android.core.recognition.RecognitionSegmenter
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.AudioInput
import com.captions.android.ports.DirectRecognitionSession
import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.SampleRecognitionSession
import com.captions.android.ports.SettingsStore
import com.captions.android.ports.TranslationSession
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

    @Test
    fun recognitionEngineSelectionPersists() {
        val settings = MemorySettingsStore()
        val viewModel = SessionViewModel(settings)

        viewModel.setRecognitionEngine(RecognitionEngine.AndroidSystem)

        assertEquals(
            RecognitionEngine.AndroidSystem,
            SessionViewModel(settings).state.value.recognitionEngine,
        )
    }

    @Test
    fun localRecognitionLoadsBeforeMicrophoneCaptureAndPublishesOneCue() {
        val audio = FakeAudioInput()
        val recognition = FakeSampleRecognitionSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(audio, viewModel, recognition)

        controller.start()
        assertEquals(0, audio.startCount)
        assertFalse(viewModel.state.value.running)
        assertTrue(viewModel.state.value.starting)

        recognition.ready()
        assertEquals(1, audio.startCount)
        assertTrue(viewModel.state.value.running)
        assertFalse(viewModel.state.value.starting)

        recognition.update(RecognitionUpdate("hello world", endpoint = false))
        recognition.update(RecognitionUpdate("hello world", endpoint = true))
        assertEquals(1, viewModel.state.value.entries.size)
        assertEquals("hello world", viewModel.state.value.entries.single().source)
        assertTrue(viewModel.state.value.entries.single().current)
    }

    @Test
    fun disablingTheMicrophoneCancelsAStartingSession() {
        val recognition = FakeSampleRecognitionSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(
            audioInput = FakeAudioInput(),
            viewModel = viewModel,
            recognitionSession = recognition,
        )

        controller.start()
        assertTrue(viewModel.state.value.starting)
        controller.setMicrophoneEnabled(false)

        assertFalse(viewModel.state.value.starting)
        assertFalse(viewModel.state.value.running)
    }

    @Test
    fun systemRecognitionDoesNotOpenTheAppAudioInput() {
        val audio = FakeAudioInput()
        val system = FakeDirectRecognitionSession()
        val viewModel = SessionViewModel(MemorySettingsStore()).apply {
            setRecognitionEngine(RecognitionEngine.AndroidSystem)
        }
        val controller = AndroidSessionController(
            audioInput = audio,
            viewModel = viewModel,
            systemRecognitionSession = system,
        )

        controller.start()
        system.ready()

        assertEquals(0, audio.startCount)
        assertEquals(1, system.startCount)
        assertTrue(viewModel.state.value.running)
    }

    @Test
    fun partialAndCompletedCueUseTheirSeparateTranslationPaths() {
        val audio = FakeAudioInput()
        val recognition = FakeSampleRecognitionSession()
        val translation = FakeTranslationSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(
            audioInput = audio,
            viewModel = viewModel,
            recognitionSession = recognition,
            translationSession = translation,
        )

        controller.start()
        recognition.ready()
        recognition.update(RecognitionUpdate("unfinished", endpoint = false))
        assertEquals(listOf(1L to "unfinished"), translation.previews)

        recognition.update(RecognitionUpdate("finished sentence", endpoint = true))
        assertEquals(listOf(1L to "finished sentence"), translation.commits)
        translation.completeFinal(1L, "完整译文")
        assertEquals("完整译文", viewModel.state.value.entries.single().translation)
    }

    @Test
    fun laterSourcePartialsPreserveTheVisiblePreviewTranslation() {
        val recognition = FakeSampleRecognitionSession()
        val translation = FakeTranslationSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(
            audioInput = FakeAudioInput(),
            viewModel = viewModel,
            recognitionSession = recognition,
            translationSession = translation,
        )

        controller.start()
        recognition.ready()
        recognition.update(RecognitionUpdate("hello", endpoint = false))
        translation.completePreview(1L, "你好")
        recognition.update(RecognitionUpdate("hello world", endpoint = false))

        assertEquals("hello world", viewModel.state.value.entries.single().source)
        assertEquals("你好", viewModel.state.value.entries.single().translation)
    }

    @Test
    fun completedCuesProvideEarlierSourcesAsTranslationContext() {
        val recognition = FakeSampleRecognitionSession()
        val translation = FakeTranslationSession()
        val controller = AndroidSessionController(
            audioInput = FakeAudioInput(),
            viewModel = SessionViewModel(MemorySettingsStore()),
            recognitionSession = recognition,
            translationSession = translation,
        )

        controller.start()
        recognition.ready()
        recognition.update(RecognitionUpdate("first", endpoint = true))
        recognition.update(RecognitionUpdate("second", endpoint = true))

        assertEquals(emptyList<String>(), translation.contexts[0])
        assertEquals(listOf("first"), translation.contexts[1])
    }

    @Test
    fun stablePunctuationCommitsBeforeTheRecognizerEndpoint() {
        val recognition = FakeSampleRecognitionSession()
        val translation = FakeTranslationSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(
            audioInput = FakeAudioInput(),
            viewModel = viewModel,
            recognitionSession = recognition,
            translationSession = translation,
            segmenter = RecognitionSegmenter(nowMillis = { 1_000L }),
        )
        controller.start()
        recognition.ready()

        recognition.update(RecognitionUpdate("Hello world.", endpoint = false))
        recognition.update(RecognitionUpdate("Hello world.", endpoint = false))

        assertEquals(listOf(1L to "Hello world."), translation.commits)
        assertEquals("Hello world.", viewModel.state.value.entries.single().source)
        assertTrue(viewModel.state.value.entries.single().current)
    }

    @Test
    fun emptyEndpointFlushesTheLastPartialInsteadOfDroppingIt() {
        val recognition = FakeSampleRecognitionSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(
            audioInput = FakeAudioInput(),
            viewModel = viewModel,
            recognitionSession = recognition,
        )
        controller.start()
        recognition.ready()

        recognition.update(RecognitionUpdate("keep this partial", endpoint = false))
        recognition.update(RecognitionUpdate("", endpoint = true))

        assertEquals("keep this partial", viewModel.state.value.entries.single().source)
        assertTrue(viewModel.state.value.entries.single().current)
    }

    @Test
    fun longSpeechCreatesACommittedCueAndKeepsTheTailLive() {
        val recognition = FakeSampleRecognitionSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(
            audioInput = FakeAudioInput(),
            viewModel = viewModel,
            recognitionSession = recognition,
            segmenter = RecognitionSegmenter(
                maxChars = 20,
                splitLookbackChars = 4,
                splitLookaheadChars = 5,
                nowMillis = { 1_000L },
            ),
        )
        controller.start()
        recognition.ready()

        recognition.update(
            RecognitionUpdate("one two three four five six", endpoint = false),
        )

        assertEquals(2, viewModel.state.value.entries.size)
        assertFalse(viewModel.state.value.entries.first().current)
        assertTrue(viewModel.state.value.entries.last().current)
        assertEquals("six", viewModel.state.value.entries.last().source)
    }

    @Test
    fun disablingTheMicrophoneCommitsTheLiveCueBeforeResume() {
        val recognition = FakeSampleRecognitionSession()
        val viewModel = SessionViewModel(MemorySettingsStore())
        val controller = AndroidSessionController(
            audioInput = FakeAudioInput(),
            viewModel = viewModel,
            recognitionSession = recognition,
        )
        controller.start()
        recognition.ready()
        recognition.update(RecognitionUpdate("first phrase", endpoint = false))

        controller.setMicrophoneEnabled(false)
        controller.setMicrophoneEnabled(true)
        recognition.ready()
        recognition.update(RecognitionUpdate("second phrase", endpoint = false))

        assertEquals(2, viewModel.state.value.entries.size)
        assertEquals("first phrase", viewModel.state.value.entries.first().source)
        assertFalse(viewModel.state.value.entries.first().current)
        assertEquals("second phrase", viewModel.state.value.entries.last().source)
        assertTrue(viewModel.state.value.entries.last().current)
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

    private class FakeSampleRecognitionSession : SampleRecognitionSession {
        private var readyCallback: () -> Unit = {}
        private var updateCallback: (RecognitionUpdate) -> Unit = {}

        override fun start(
            onReady: () -> Unit,
            onUpdate: (RecognitionUpdate) -> Unit,
            onError: (String) -> Unit,
        ) {
            readyCallback = onReady
            updateCallback = onUpdate
        }

        override fun accept(samples: ShortArray): Boolean = true
        override fun stop() = Unit
        override fun close() = Unit
        fun ready() = readyCallback()
        fun update(update: RecognitionUpdate) = updateCallback(update)
    }

    private class FakeDirectRecognitionSession : DirectRecognitionSession {
        var startCount = 0
        private var readyCallback: () -> Unit = {}

        override fun start(
            onReady: () -> Unit,
            onUpdate: (RecognitionUpdate) -> Unit,
            onError: (String) -> Unit,
        ) {
            startCount += 1
            readyCallback = onReady
        }

        override fun stop() = Unit
        override fun close() = Unit
        fun ready() = readyCallback()
    }

    private class FakeTranslationSession : TranslationSession {
        val previews = mutableListOf<Pair<Long, String>>()
        val commits = mutableListOf<Pair<Long, String>>()
        val contexts = mutableListOf<List<String>>()
        private var previewResult: (Long, String) -> Unit = { _, _ -> }
        private var finalResult: (Long, String) -> Unit = { _, _ -> }

        override fun preview(
            cueId: Long,
            text: String,
            context: List<String>,
            settings: TranslationSettings,
            onResult: (Long, String) -> Unit,
        ): Boolean {
            previews += cueId to text
            previewResult = onResult
            return true
        }

        override fun commit(
            cueId: Long,
            text: String,
            context: List<String>,
            settings: TranslationSettings,
            onResult: (Long, String) -> Unit,
            onError: (String) -> Unit,
        ): Boolean {
            commits += cueId to text
            contexts += context
            finalResult = onResult
            return true
        }

        override fun cancelPending() = Unit
        override fun close() = Unit
        fun completePreview(cueId: Long, text: String) = previewResult(cueId, text)
        fun completeFinal(cueId: Long, text: String) = finalResult(cueId, text)
    }

    private class MemorySettingsStore : SettingsStore {
        private var settings = AppearanceSettings()
        private var engine = RecognitionEngine.Nemotron

        override fun loadAppearance(): AppearanceSettings = settings

        override fun saveAppearance(settings: AppearanceSettings) {
            this.settings = settings
        }

        override fun loadRecognitionEngine(): RecognitionEngine = engine

        override fun saveRecognitionEngine(engine: RecognitionEngine) {
            this.engine = engine
        }

        override fun loadTranslation(): TranslationSettings = TranslationSettings()

        override fun saveTranslation(settings: TranslationSettings) = Unit
    }
}
