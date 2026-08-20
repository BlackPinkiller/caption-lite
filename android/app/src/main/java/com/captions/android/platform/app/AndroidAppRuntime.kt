package com.captions.android.platform.app

import android.content.Context
import com.captions.android.core.recognition.QueuedRecognitionSession
import com.captions.android.core.recognition.RecognitionSegmenter
import com.captions.android.core.session.SessionStore
import com.captions.android.core.session.NemotronModel
import com.captions.android.core.translation.RealtimeTranslationSession
import com.captions.android.core.translation.TranslationRouter
import com.captions.android.platform.audio.AndroidMicrophoneInput
import com.captions.android.platform.model.AndroidNemotronModelManager
import com.captions.android.platform.recognition.AndroidSystemRecognitionSession
import com.captions.android.platform.recognition.AndroidSpeechModelManager
import com.captions.android.platform.recognition.SherpaNemotronRecognitionFactory
import com.captions.android.platform.session.AndroidSessionController
import com.captions.android.platform.settings.AndroidSettingsStore
import com.captions.android.platform.translation.DeepLTranslator
import com.captions.android.platform.translation.Google2Translator
import com.captions.android.platform.translation.AndroidOnDeviceTranslator
import com.captions.android.platform.translation.AndroidTranslationModelManager
import com.captions.android.platform.translation.Gemma4ModelManager
import com.captions.android.platform.translation.OpenAICompatibleTranslator
import com.captions.android.platform.translation.gemma4Translator
import com.captions.android.platform.translation.UrlConnectionHttpClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

class AndroidAppRuntime(context: Context) : AutoCloseable {
    private val appContext = context.applicationContext
    private val settingsStore = AndroidSettingsStore(appContext)

    val sessionStore = SessionStore(settingsStore)
    val recognitionModelManager = AndroidNemotronModelManager(
        appContext,
        sessionStore.state.value.nemotronModel,
    )
    val systemRecognitionModelManager = AndroidSpeechModelManager(appContext)
    val translationModelManager = AndroidTranslationModelManager(appContext)
    val gemma4ModelManager = Gemma4ModelManager(appContext)
    private val mutableAppVisible = MutableStateFlow(false)
    val appVisible = mutableAppVisible.asStateFlow()

    private val translationSession = RealtimeTranslationSession(
        UrlConnectionHttpClient().let { httpClient ->
            TranslationRouter(
                local = AndroidOnDeviceTranslator(appContext, translationModelManager),
                google2 = Google2Translator(httpClient),
                deepL = DeepLTranslator(httpClient),
                openAICompatible = OpenAICompatibleTranslator(httpClient),
                gemma4 = gemma4Translator(gemma4ModelManager),
            )
        },
    )

    private val recognitionSession = QueuedRecognitionSession(
        SherpaNemotronRecognitionFactory(
            recognitionModelManager::modelDirectory,
            appContext.assets,
        ),
    )

    val sessionController = AndroidSessionController(
        audioInput = AndroidMicrophoneInput(),
        viewModel = sessionStore,
        segmenter = RecognitionSegmenter(
            splitPunctuation = sessionStore.state.value.splitPunctuation,
        ),
        recognitionSession = recognitionSession,
        systemRecognitionSession = AndroidSystemRecognitionSession(
            context = appContext,
            language = {
                val requested = sessionStore.state.value.translationSettings.sourceLanguage
                systemRecognitionModelManager.installedLanguageTag(requested) ?: requested
            },
            modelReady = systemRecognitionModelManager::isReady,
        ),
        translationSession = translationSession,
    )

    fun applyTranslationSettings() {
        translationSession.cancelPending()
        translationModelManager.configure(sessionStore.state.value.translationSettings)
        gemma4ModelManager.configure(sessionStore.state.value.translationSettings)
    }

    fun applyNemotronModel(model: NemotronModel) {
        recognitionSession.reload()
        recognitionModelManager.configure(model)
    }

    fun setAppVisible(visible: Boolean) {
        mutableAppVisible.value = visible
    }

    override fun close() {
        sessionController.close()
        recognitionModelManager.close()
        systemRecognitionModelManager.close()
        translationModelManager.close()
        gemma4ModelManager.close()
    }
}
