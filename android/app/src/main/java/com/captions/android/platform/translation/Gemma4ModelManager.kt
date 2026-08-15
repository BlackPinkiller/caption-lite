package com.captions.android.platform.translation

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.util.Log
import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.TranslationModelManager
import com.google.ai.edge.litertlm.Backend
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class Gemma4ModelManager(context: Context) : TranslationModelManager {
    private val appContext = context.applicationContext
    private val downloadManager = appContext.getSystemService(DownloadManager::class.java)
    private val preferences = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Missing))
    private var monitorJob: Job? = null
    private val engineThread = Executors.newSingleThreadExecutor { task ->
        Thread(task, "captions-gemma4").apply { isDaemon = true }
    }
    private val engineLoading = AtomicBoolean(false)
    private val engine = Gemma4Engine(appContext.cacheDir.absolutePath)

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    private var settings = TranslationSettings()

    init {
        refresh()
    }

    fun modelFile(): File = File(modelDirectory(), MODEL_FILE_NAME)

    fun generate(prompt: String, maxTokens: Int): String = engine.generate(prompt, maxTokens)

    override fun configure(settings: TranslationSettings) {
        this.settings = settings
        if (settings.engine != TranslationEngine.Gemma4) {
            unloadEngine()
            return
        }
        refresh()
    }

    override fun download() {
        if (state.value.phase in setOf(ModelPhase.Downloading, ModelPhase.Preparing, ModelPhase.Ready)) {
            return
        }
        if (modelReady()) {
            refresh()
            return
        }
        monitorJob?.cancel()
        monitorJob = scope.launch {
            val enqueued = runCatching {
                cleanupFailedDownload()
                modelDirectory().mkdirs()
                val request = DownloadManager.Request(Uri.parse(MODEL_URL))
                    .setTitle("Gemma 4 · ${MODEL_FILE_NAME}")
                    .setDescription("实时字幕 · 约 2.0 GB")
                    .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
                    .setDestinationUri(Uri.fromFile(modelFile()))
                    .setAllowedOverRoaming(false)
                preferences.edit().putLong(DOWNLOAD_ID_KEY, downloadManager.enqueue(request)).apply()
            }.onFailure {
                cleanupFailedDownload()
                mutableState.value = ModelState(ModelPhase.Error, detail = "无法开始下载")
            }.isSuccess
            if (enqueued) {
                mutableState.value = ModelState(ModelPhase.Downloading)
                monitorDownloads()
            }
        }
    }

    private fun refresh() {
        monitorJob?.cancel()
        monitorJob = scope.launch {
            when {
                modelReady() -> {
                    loadEngine()
                    mutableState.value = ModelState(ModelPhase.Ready)
                }
                isDownloading() -> monitorDownloads()
                modelFile().isFile -> verifyModel()
                else -> mutableState.value = ModelState(ModelPhase.Missing)
            }
        }
    }

    private suspend fun monitorDownloads() {
        val id = preferences.getLong(DOWNLOAD_ID_KEY, -1L)
        if (id < 0) {
            cleanupFailedDownload()
            mutableState.value = ModelState(ModelPhase.Error, detail = "下载已中断，请重试")
            return
        }
        while (scope.isActive) {
            val result = queryDownload(id)
            if (result == null || result.status == DownloadManager.STATUS_FAILED) {
                cleanupFailedDownload()
                mutableState.value = ModelState(ModelPhase.Error, detail = "下载失败，请重试")
                return
            }
            if (result.status == DownloadManager.STATUS_SUCCESSFUL) {
                verifyModel()
                return
            }
            val progress = ((result.downloadedBytes * 100) / MODEL_SIZE).toInt().coerceIn(0, 100)
            mutableState.value = ModelState(ModelPhase.Downloading, progressPercent = progress)
            delay(POLL_INTERVAL_MILLIS)
        }
    }

    private fun queryDownload(id: Long): DownloadResult? {
        downloadManager.query(DownloadManager.Query().setFilterById(id)).use { cursor ->
            if (!cursor.moveToFirst()) return null
            return DownloadResult(
                status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS)),
                downloadedBytes = cursor.getLong(
                    cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR),
                ),
            )
        }
    }

    private fun verifyModel() {
        mutableState.value = ModelState(ModelPhase.Preparing)
        runCatching {
            val file = modelFile()
            require(file.length() == MODEL_SIZE) { "模型大小不正确" }
            require(file.sha256() == MODEL_SHA256) { "模型校验失败" }
            readyMarker().writeText(MODEL_REVISION)
            clearDownloadIds()
            loadEngine()
        }.onSuccess {
            mutableState.value = ModelState(ModelPhase.Ready)
        }.onFailure { error ->
            cleanupFailedDownload()
            mutableState.value = ModelState(
                ModelPhase.Error,
                detail = error.message ?: "模型准备失败",
            )
        }
    }

    private fun modelReady(): Boolean =
        modelFile().isFile && modelFile().length() == MODEL_SIZE &&
            readyMarker().takeIf(File::isFile)?.readText() == MODEL_REVISION

    private fun isDownloading(): Boolean {
        val id = preferences.getLong(DOWNLOAD_ID_KEY, -1L)
        if (id < 0) return false
        val result = queryDownload(id) ?: return false
        return result.status == DownloadManager.STATUS_RUNNING ||
            result.status == DownloadManager.STATUS_PENDING ||
            result.status == DownloadManager.STATUS_PAUSED
    }

    private fun loadEngine() {
        if (settings.engine != TranslationEngine.Gemma4) return
        if (!engine.loaded && engineLoading.compareAndSet(false, true)) {
            engineThread.execute {
                runCatching {
                    val ok = engine.load(modelFile().absolutePath, Backend.GPU())
                    Log.d(LOG_TAG, "load engine ok=$ok")
                    if (!ok) {
                        mutableState.value = ModelState(ModelPhase.Error, detail = "模型加载失败")
                    }
                }.onFailure {
                    Log.e(LOG_TAG, "load engine failed", it)
                    mutableState.value = ModelState(ModelPhase.Error, detail = "模型加载失败")
                }.also {
                    engineLoading.set(false)
                }
            }
        }
    }

    private fun unloadEngine() {
        if (engine.loaded || engineLoading.get()) {
            engineThread.execute {
                engine.close()
                engineLoading.set(false)
            }
        }
    }

    override fun isReady(settings: TranslationSettings): Boolean =
        settings.engine == TranslationEngine.Gemma4 &&
            modelReady() &&
            engine.loaded

    override fun close() {
        scope.cancel()
        monitorJob?.cancel()
        engineThread.execute { engine.close() }
        engineThread.shutdown()
    }

    private fun cleanupFailedDownload() {
        val id = preferences.getLong(DOWNLOAD_ID_KEY, -1L)
        if (id >= 0) downloadManager.remove(id)
        clearDownloadIds()
        modelDirectory().deleteRecursively()
    }

    private fun clearDownloadIds() {
        preferences.edit().remove(DOWNLOAD_ID_KEY).apply()
    }

    private fun readyMarker(): File = File(modelDirectory(), ".ready")

    private fun modelDirectory(): File = File(
        requireNotNull(appContext.getExternalFilesDir(null)),
        "models/Gemma4-E2B",
    )

    private data class DownloadResult(val status: Int, val downloadedBytes: Long)

    private companion object {
        const val LOG_TAG = "CaptionsGemma4"
        const val PREFERENCES = "captions_gemma4_downloads"
        const val DOWNLOAD_ID_KEY = "gemma4_download_id"
        const val POLL_INTERVAL_MILLIS = 750L
        const val MODEL_FILE_NAME = "gemma-4-E2B-it-gpu.litertlm"
        const val MODEL_SIZE = 2_008_432_640L
        const val MODEL_SHA256 = "a53a59001894c58e6bdb5b9b227709f91a2e3e556baa7d85acf9c55402ba5cf5"
        const val MODEL_REVISION = "a53a59001894c58e6bdb5b9b227709f91a2e3e556baa7d85acf9c55402ba5cf5"
        const val MODEL_URL =
            "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/$MODEL_FILE_NAME"
    }
}

private fun File.sha256(): String {
    val digest = MessageDigest.getInstance("SHA-256")
    inputStream().buffered().use { input ->
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        var count = input.read(buffer)
        while (count >= 0) {
            if (count > 0) digest.update(buffer, 0, count)
            count = input.read(buffer)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}
