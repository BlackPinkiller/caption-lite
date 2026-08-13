package com.captions.android.platform.translation

import android.content.Context
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.TranslationModelManager
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.TranslatorOptions
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class GoogleTranslationModelManager(context: Context) : TranslationModelManager {
    private val preferences = context.applicationContext.getSharedPreferences(
        PREFERENCES,
        Context.MODE_PRIVATE,
    )
    private val executor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "captions-translation-model").apply { isDaemon = true }
    }
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Missing))
    @Volatile
    private var settings = TranslationSettings()

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    override fun configure(settings: TranslationSettings) {
        this.settings = settings
        mutableState.value = if (isReady(settings)) {
            ModelState(ModelPhase.Ready)
        } else {
            ModelState(ModelPhase.Missing)
        }
    }

    override fun download() {
        if (mutableState.value.phase in setOf(ModelPhase.Downloading, ModelPhase.Preparing)) return
        val requested = settings
        mutableState.value = ModelState(ModelPhase.Preparing)
        executor.execute {
            val translator = Translation.getClient(options(requested))
            runCatching {
                Tasks.await(
                    translator.downloadModelIfNeeded(
                        DownloadConditions.Builder().requireWifi().build(),
                    ),
                    DOWNLOAD_TIMEOUT_MINUTES,
                    TimeUnit.MINUTES,
                )
            }.onSuccess {
                preferences.edit().putBoolean(readyKey(requested), true).apply()
                if (requested == settings) mutableState.value = ModelState(ModelPhase.Ready)
            }.onFailure {
                if (requested == settings) {
                    mutableState.value = ModelState(
                        ModelPhase.Error,
                        detail = "无法下载本地翻译模型",
                    )
                }
            }
            translator.close()
        }
    }

    override fun isReady(settings: TranslationSettings): Boolean =
        preferences.getBoolean(readyKey(settings), false)

    override fun close() {
        executor.shutdownNow()
    }

    private fun readyKey(settings: TranslationSettings): String =
        "ready_${settings.sourceLanguage}_${settings.targetLanguage}"

    companion object {
        private const val PREFERENCES = "captions_translation_models"
        private const val DOWNLOAD_TIMEOUT_MINUTES = 10L

        fun options(settings: TranslationSettings): TranslatorOptions = TranslatorOptions.Builder()
            .setSourceLanguage(settings.sourceLanguage)
            .setTargetLanguage(settings.targetLanguage)
            .build()
    }
}
