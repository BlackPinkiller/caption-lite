package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.TranslationModelManager
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.TranslateRemoteModel
import com.google.mlkit.nl.translate.TranslatorOptions
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class GoogleTranslationModelManager : TranslationModelManager {
    private val modelManager = RemoteModelManager.getInstance()
    private val executor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "captions-translation-model").apply { isDaemon = true }
    }
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Missing))
    private val configurationId = AtomicLong()
    @Volatile
    private var settings = TranslationSettings()
    @Volatile
    private var verifiedSettings: TranslationSettings? = null

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    override fun configure(settings: TranslationSettings) {
        this.settings = settings
        verifiedSettings = null
        val requestedId = configurationId.incrementAndGet()
        mutableState.value = ModelState(ModelPhase.Preparing)
        executor.execute {
            val ready = runCatching { modelsAreDownloaded(settings) }
            if (requestedId != configurationId.get()) return@execute
            ready.onSuccess { downloaded ->
                verifiedSettings = settings.takeIf { downloaded }
                mutableState.value = ModelState(
                    if (downloaded) ModelPhase.Ready else ModelPhase.Missing,
                )
            }.onFailure {
                mutableState.value = ModelState(
                    ModelPhase.Error,
                    detail = "无法检查本地翻译模型",
                )
            }
        }
    }

    override fun download() {
        if (mutableState.value.phase in setOf(ModelPhase.Downloading, ModelPhase.Preparing)) return
        val requested = settings
        val requestedId = configurationId.incrementAndGet()
        verifiedSettings = null
        mutableState.value = ModelState(ModelPhase.Downloading)
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
                check(modelsAreDownloaded(requested))
            }.onSuccess {
                if (requestedId == configurationId.get()) {
                    verifiedSettings = requested
                    mutableState.value = ModelState(ModelPhase.Ready)
                }
            }.onFailure {
                if (requestedId == configurationId.get()) {
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
        verifiedSettings == settings && mutableState.value.phase == ModelPhase.Ready

    override fun close() {
        configurationId.incrementAndGet()
        executor.shutdownNow()
    }

    private fun modelsAreDownloaded(settings: TranslationSettings): Boolean =
        requiredDownloadLanguages(settings).all { language ->
            val model = TranslateRemoteModel.Builder(language).build()
            Tasks.await(
                modelManager.isModelDownloaded(model),
                STATUS_TIMEOUT_SECONDS,
                TimeUnit.SECONDS,
            )
        }

    companion object {
        private const val DOWNLOAD_TIMEOUT_MINUTES = 10L
        private const val STATUS_TIMEOUT_SECONDS = 5L

        fun options(settings: TranslationSettings): TranslatorOptions = TranslatorOptions.Builder()
            .setSourceLanguage(settings.sourceLanguage)
            .setTargetLanguage(settings.targetLanguage)
            .build()
    }
}

internal fun requiredDownloadLanguages(settings: TranslationSettings): Set<String> =
    setOf(settings.sourceLanguage, settings.targetLanguage) - "en"
