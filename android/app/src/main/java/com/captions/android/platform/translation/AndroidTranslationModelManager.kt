package com.captions.android.platform.translation

import android.app.PendingIntent
import android.content.Context
import android.view.translation.TranslationCapability
import android.view.translation.TranslationManager
import android.view.translation.TranslationSpec
import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.TranslationModelManager
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong
import java.util.function.Consumer
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class AndroidTranslationModelManager(context: Context) : TranslationModelManager {
    private val manager = context.getSystemService(TranslationManager::class.java)
    private val executor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "captions-translation-capabilities").apply { isDaemon = true }
    }
    private val requestId = AtomicLong()
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Preparing))
    private val capabilityListener = Consumer<TranslationCapability> { capability ->
        val current = settings
        val matches = capability.matches(current)
        val applies = matches &&
            (
                capability.exactVariant(current) ||
                    capability.state == TranslationCapability.STATE_ON_DEVICE
                )
        if (applies) updateState(capability)
    }
    @Volatile
    private var settings = TranslationSettings()

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    init {
        manager?.addOnDeviceTranslationCapabilityUpdateListener(executor, capabilityListener)
    }

    override fun configure(settings: TranslationSettings) {
        this.settings = settings
        val currentId = requestId.incrementAndGet()
        if (settings.engine != TranslationEngine.GoogleOnDevice) return
        if (sameLanguage(settings.sourceLanguage, settings.targetLanguage)) {
            mutableState.value = ModelState(ModelPhase.Ready)
            return
        }
        mutableState.value = ModelState(ModelPhase.Preparing)
        val currentManager = manager
        if (currentManager == null) {
            mutableState.value = ModelState(ModelPhase.Error, detail = "系统本地翻译不可用")
            return
        }
        executor.execute {
            runCatching {
                currentManager.getOnDeviceTranslationCapabilities(
                    TranslationSpec.DATA_FORMAT_TEXT,
                    TranslationSpec.DATA_FORMAT_TEXT,
                )
            }.onSuccess { capabilities ->
                if (currentId != requestId.get()) return@onSuccess
                val matches = capabilities.filter { it.matches(settings) }
                val capability = matches.firstOrNull { it.exactVariant(settings) }
                    ?: matches.firstOrNull { it.state == TranslationCapability.STATE_ON_DEVICE }
                    ?: matches.firstOrNull()
                if (capability == null) {
                    mutableState.value = ModelState(
                        ModelPhase.Error,
                        detail = "系统不支持该语言组合",
                    )
                } else {
                    updateState(capability)
                }
            }.onFailure {
                if (currentId == requestId.get()) {
                    mutableState.value = ModelState(
                        ModelPhase.Error,
                        detail = "无法检查系统翻译语言",
                    )
                }
            }
        }
    }

    override fun download() {
        val settingsIntent = manager?.onDeviceTranslationSettingsActivityIntent
        if (settingsIntent == null) {
            mutableState.value = ModelState(ModelPhase.Error, detail = "系统没有翻译模型设置")
            return
        }
        runCatching { settingsIntent.send() }.onFailure { error ->
            if (error is PendingIntent.CanceledException) {
                mutableState.value = ModelState(ModelPhase.Error, detail = "无法打开系统翻译设置")
            }
        }
    }

    override fun isReady(settings: TranslationSettings): Boolean =
        sameLanguage(settings.sourceLanguage, settings.targetLanguage) ||
            (
                this.settings.samePair(settings) &&
                    mutableState.value.phase == ModelPhase.Ready
                )

    override fun close() {
        requestId.incrementAndGet()
        manager?.removeOnDeviceTranslationCapabilityUpdateListener(capabilityListener)
        executor.shutdownNow()
    }

    private fun updateState(capability: TranslationCapability) {
        mutableState.value = when (capability.state) {
            TranslationCapability.STATE_ON_DEVICE -> ModelState(ModelPhase.Ready)
            TranslationCapability.STATE_DOWNLOADING -> ModelState(ModelPhase.Downloading)
            TranslationCapability.STATE_AVAILABLE_TO_DOWNLOAD -> ModelState(ModelPhase.Missing)
            else -> ModelState(ModelPhase.Error, detail = "系统不支持该语言组合")
        }
    }
}

internal fun TranslationCapability.matches(settings: TranslationSettings): Boolean =
    sameLanguage(sourceSpec.locale.toLanguageTag(), settings.sourceLanguage) &&
        sameLanguage(targetSpec.locale.toLanguageTag(), settings.targetLanguage)

internal fun TranslationCapability.exactVariant(settings: TranslationSettings): Boolean =
    sourceSpec.locale.toLanguageTag().equals(settings.sourceLanguage, ignoreCase = true) &&
        targetSpec.locale.toLanguageTag().equals(settings.targetLanguage, ignoreCase = true)

internal fun TranslationSettings.samePair(other: TranslationSettings): Boolean =
    sameLanguage(sourceLanguage, other.sourceLanguage) &&
        sameLanguage(targetLanguage, other.targetLanguage)

internal fun sameLanguage(first: String, second: String): Boolean =
    first.substringBefore('-').equals(second.substringBefore('-'), ignoreCase = true)
