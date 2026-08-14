package com.captions.android.platform.translation

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.util.Log
import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.hymt.HyMt2Engine
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.TranslationModelManager
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

class HyMt2ModelManager(context: Context) : TranslationModelManager {
    private val appContext = context.applicationContext
    private val downloadManager = appContext.getSystemService(DownloadManager::class.java)
    private val preferences = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Missing))
    private var monitorJob: Job? = null
    private val engineThread = Executors.newSingleThreadExecutor { task ->
        Thread(task, "captions-hymt").apply { isDaemon = true }
    }
    private val engineLoading = AtomicBoolean(false)

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    private var settings = TranslationSettings()

    init {
        refresh()
    }

    fun modelFile(): File = File(modelDirectory(), MODEL_FILE_NAME)

    override fun configure(settings: TranslationSettings) {
        this.settings = settings
        if (settings.engine != TranslationEngine.HyMt2) {
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
                    .setTitle("HyMT2 · ${MODEL_FILE_NAME}")
                    .setDescription("实时字幕 · 约 440 MB")
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
        if (settings.engine != TranslationEngine.HyMt2) return
        if (!HyMt2Engine.loaded && engineLoading.compareAndSet(false, true)) {
            engineThread.execute {
                runCatching {
                    val ok = HyMt2Engine.load(modelFile().absolutePath, N_CTX, N_THREADS)
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
        if (HyMt2Engine.loaded || engineLoading.get()) {
            engineThread.execute {
                HyMt2Engine.unload()
                engineLoading.set(false)
            }
        }
    }

    override fun isReady(settings: TranslationSettings): Boolean =
        settings.engine == TranslationEngine.HyMt2 &&
            modelReady() &&
            HyMt2Engine.loaded

    override fun close() {
        scope.cancel()
        monitorJob?.cancel()
        engineThread.execute { HyMt2Engine.unload() }
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
        "models/HyMT2-1.8B-1.25Bit",
    )

    private data class DownloadResult(val status: Int, val downloadedBytes: Long)

    private companion object {
        const val LOG_TAG = "CaptionsHyMt2"
        const val PREFERENCES = "captions_hymt_downloads"
        const val DOWNLOAD_ID_KEY = "hymt_download_id"
        const val POLL_INTERVAL_MILLIS = 750L
        const val MODEL_FILE_NAME = "Hy-MT2-1.8B-1.25Bit.gguf"
        const val MODEL_SIZE = 461_860_800L
        const val MODEL_SHA256 = "cc497fe8f033b52b3b8b00a7669e9661435432f9d4cd43f7ed24400c01507a93"
        const val MODEL_REVISION = "cc497fe8f033b52b3b8b00a7669e9661435432f9d4cd43f7ed24400c01507a93"
        const val MODEL_URL =
            "https://huggingface.co/tencent/Hy-MT2-1.8B-1.25Bit-GGUF/resolve/main/$MODEL_FILE_NAME"
        const val N_CTX = 1024
        const val N_THREADS = 4
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
