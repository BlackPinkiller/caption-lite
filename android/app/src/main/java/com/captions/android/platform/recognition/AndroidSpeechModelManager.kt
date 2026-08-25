package com.captions.android.platform.recognition

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.speech.ModelDownloadListener
import android.speech.RecognitionSupport
import android.speech.RecognitionSupportCallback
import android.speech.SpeechRecognizer
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.RecognitionLanguageModelManager
import java.util.Locale
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class AndroidSpeechModelManager(context: Context) : RecognitionLanguageModelManager {
    private val appContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private val requestId = AtomicLong()
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Preparing))
    private var recognizer: SpeechRecognizer? = null
    private var refreshAction: Runnable? = null
    @Volatile
    private var language = "en"
    @Volatile
    private var verifiedLanguage: String? = null
    @Volatile
    private var installedLanguageTag: String? = null

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    override fun configure(language: String) {
        this.language = language
        verifiedLanguage = null
        installedLanguageTag = null
        refresh()
    }

    override fun refresh() {
        val currentId = requestId.incrementAndGet()
        mutableState.value = ModelState(ModelPhase.Preparing)
        runOnMain {
            cancelRefresh()
            releaseRecognizer()
            if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(appContext)) {
                mutableState.value = ModelState(ModelPhase.Error, detail = "系统本地识别不可用")
                return@runOnMain
            }
            val current = SpeechRecognizer.createOnDeviceSpeechRecognizer(appContext)
            recognizer = current
            current.checkRecognitionSupport(
                systemRecognitionIntent(language),
                appContext.mainExecutor,
                object : RecognitionSupportCallback {
                    override fun onSupportResult(support: RecognitionSupport) {
                        if (currentId != requestId.get()) return
                        val requested = language
                        when {
                            matchingLanguage(requested, support.installedOnDeviceLanguages) != null -> {
                                verifiedLanguage = requested
                                installedLanguageTag = matchingLanguage(
                                    requested,
                                    support.installedOnDeviceLanguages,
                                )
                                mutableState.value = ModelState(ModelPhase.Ready)
                            }
                            supportsLanguage(requested, support.pendingOnDeviceLanguages) -> {
                                mutableState.value = ModelState(
                                    ModelPhase.Downloading,
                                    detail = "等待系统下载",
                                )
                                scheduleRefresh()
                            }
                            supportsLanguage(requested, support.supportedOnDeviceLanguages) -> {
                                mutableState.value = ModelState(ModelPhase.Missing)
                            }
                            else -> {
                                mutableState.value = ModelState(
                                    ModelPhase.Error,
                                    detail = "系统识别不支持该语言",
                                )
                            }
                        }
                        releaseIfCurrent(current)
                    }

                    override fun onError(error: Int) {
                        if (currentId == requestId.get()) {
                            mutableState.value = ModelState(
                                ModelPhase.Error,
                                detail = "无法检查系统识别语言",
                            )
                        }
                        releaseIfCurrent(current)
                    }
                },
            )
        }
    }

    override fun download() {
        if (mutableState.value.phase in setOf(ModelPhase.Downloading, ModelPhase.Ready)) return
        val currentId = requestId.incrementAndGet()
        verifiedLanguage = null
        installedLanguageTag = null
        mutableState.value = ModelState(ModelPhase.Downloading)
        runOnMain {
            cancelRefresh()
            releaseRecognizer()
            if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(appContext)) {
                mutableState.value = ModelState(ModelPhase.Error, detail = "系统本地识别不可用")
                return@runOnMain
            }
            val current = SpeechRecognizer.createOnDeviceSpeechRecognizer(appContext)
            recognizer = current
            val intent = systemRecognitionIntent(language)
            current.triggerModelDownload(
                intent,
                appContext.mainExecutor,
                object : ModelDownloadListener {
                    override fun onProgress(completedPercent: Int) {
                        if (currentId == requestId.get()) {
                            mutableState.value = ModelState(
                                ModelPhase.Downloading,
                                progressPercent = completedPercent.coerceIn(0, 100),
                            )
                        }
                    }

                    override fun onSuccess() {
                        if (currentId == requestId.get()) {
                            releaseIfCurrent(current)
                            refresh()
                        } else {
                            releaseIfCurrent(current)
                        }
                    }

                    override fun onScheduled() {
                        if (currentId == requestId.get()) {
                            mutableState.value = ModelState(
                                ModelPhase.Downloading,
                                detail = "等待系统下载",
                            )
                            scheduleRefresh()
                        }
                        releaseIfCurrent(current)
                    }

                    override fun onError(error: Int) {
                        if (currentId != requestId.get()) return
                        if (error == SpeechRecognizer.ERROR_CANNOT_LISTEN_TO_DOWNLOAD_EVENTS) {
                            current.triggerModelDownload(intent)
                            mutableState.value = ModelState(
                                ModelPhase.Downloading,
                                detail = "等待系统下载",
                            )
                            scheduleRefresh()
                        } else {
                            mutableState.value = ModelState(
                                ModelPhase.Error,
                                detail = "无法下载系统识别语言",
                            )
                        }
                        releaseIfCurrent(current)
                    }
                },
            )
        }
    }

    override fun isReady(language: String): Boolean =
        verifiedLanguage?.let { sameLanguage(it, language) } == true &&
            installedLanguageTag != null && mutableState.value.phase == ModelPhase.Ready

    override fun installedLanguageTag(language: String): String? =
        installedLanguageTag.takeIf { isReady(language) }

    override fun close() {
        requestId.incrementAndGet()
        runOnMain {
            cancelRefresh()
            releaseRecognizer()
        }
    }

    private fun scheduleRefresh() {
        cancelRefresh()
        refreshAction = Runnable { refresh() }.also {
            handler.postDelayed(it, REFRESH_MILLIS)
        }
    }

    private fun cancelRefresh() {
        refreshAction?.let(handler::removeCallbacks)
        refreshAction = null
    }

    private fun releaseIfCurrent(current: SpeechRecognizer) {
        if (recognizer === current) releaseRecognizer() else current.destroy()
    }

    private fun releaseRecognizer() {
        recognizer?.destroy()
        recognizer = null
    }

    private fun runOnMain(action: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) action() else handler.post(action)
    }

    private companion object {
        const val REFRESH_MILLIS = 15_000L
    }
}

internal fun supportsLanguage(requested: String, candidates: List<String>): Boolean =
    matchingLanguage(requested, candidates) != null

internal fun matchingLanguage(requested: String, candidates: List<String>): String? =
    candidates.firstOrNull { candidate -> sameLanguage(requested, candidate) }

private fun sameLanguage(first: String, second: String): Boolean {
    val firstLocale = Locale.forLanguageTag(first)
    val secondLocale = Locale.forLanguageTag(second)
    return firstLocale.language.equals(secondLocale.language, ignoreCase = true) &&
        (
            firstLocale.country.isBlank() || secondLocale.country.isBlank() ||
                firstLocale.country.equals(secondLocale.country, ignoreCase = true)
            )
}
