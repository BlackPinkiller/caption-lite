package com.captions.android.platform.app

import android.content.Context
import com.captions.android.core.recognition.QueuedRecognitionSession
import com.captions.android.core.session.SessionStore
import com.captions.android.core.translation.RealtimeTranslationSession
import com.captions.android.core.translation.TranslationRouter
import com.captions.android.platform.audio.AndroidMicrophoneInput
import com.captions.android.platform.model.AndroidNemotronModelManager
import com.captions.android.platform.recognition.AndroidSystemRecognitionSession
import com.captions.android.platform.recognition.SherpaNemotronRecognitionFactory
import com.captions.android.platform.session.AndroidSessionController
import com.captions.android.platform.settings.AndroidSettingsStore
import com.captions.android.platform.translation.DeepLTranslator
import com.captions.android.platform.translation.Google2Translator
import com.captions.android.platform.translation.GoogleOnDeviceTranslator
import com.captions.android.platform.translation.GoogleTranslationModelManager
import com.captions.android.platform.translation.OpenAICompatibleTranslator
import com.captions.android.platform.translation.UrlConnectionHttpClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

class AndroidAppRuntime(context: Context) : AutoCloseable {
    private val appContext = context.applicationContext
    private val settingsStore = AndroidSettingsStore(appContext)

    val sessionStore = SessionStore(settingsStore)
    val recognitionModelManager = AndroidNemotronModelManager(appContext)
    val translationModelManager = GoogleTranslationModelManager()
    private val mutableAppVisible = MutableStateFlow(false)
    val appVisible = mutableAppVisible.asStateFlow()

    private val translationSession = RealtimeTranslationSession(
        UrlConnectionHttpClient().let { httpClient ->
            TranslationRouter(
                local = GoogleOnDeviceTranslator(translationModelManager),
                google2 = Google2Translator(httpClient),
                deepL = DeepLTranslator(httpClient),
                openAICompatible = OpenAICompatibleTranslator(httpClient),
            )
        },
    )

    val sessionController = AndroidSessionController(
        audioInput = AndroidMicrophoneInput(),
        viewModel = sessionStore,
        recognitionSession = QueuedRecognitionSession(
            SherpaNemotronRecognitionFactory(recognitionModelManager::modelDirectory),
        ),
        systemRecognitionSession = AndroidSystemRecognitionSession(appContext) {
            sessionStore.state.value.translationSettings.sourceLanguage
        },
        translationSession = translationSession,
    )

    fun applyTranslationSettings() {
        translationSession.cancelPending()
        translationModelManager.configure(sessionStore.state.value.translationSettings)
    }

    fun setAppVisible(visible: Boolean) {
        mutableAppVisible.value = visible
    }

    override fun close() {
        sessionController.close()
        recognitionModelManager.close()
        translationModelManager.close()
    }
}
