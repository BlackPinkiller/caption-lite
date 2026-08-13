package com.captions.android.platform.model

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.RecognitionModelManager
import java.io.File
import java.security.MessageDigest
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

class AndroidNemotronModelManager(context: Context) : RecognitionModelManager {
    private val appContext = context.applicationContext
    private val downloadManager = appContext.getSystemService(DownloadManager::class.java)
    private val preferences = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Missing))
    private var monitorJob: Job? = null

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    init {
        refresh()
    }

    override fun refresh() {
        monitorJob?.cancel()
        monitorJob = scope.launch {
            cleanupLegacyArchive()
            when {
                hasReadyMarker() -> mutableState.value = ModelState(ModelPhase.Ready)
                activeDownloadIds().isNotEmpty() -> monitorDownloads()
                allModelFilesExist() -> verifyDownloads()
                else -> mutableState.value = ModelState(ModelPhase.Missing)
            }
        }
    }

    override fun download() {
        if (state.value.phase in setOf(ModelPhase.Downloading, ModelPhase.Preparing, ModelPhase.Ready)) {
            return
        }
        monitorJob?.cancel()
        monitorJob = scope.launch {
            runCatching {
                cleanupFailedDownload()
                modelDirectory().mkdirs()
                MODEL_FILES.forEach { modelFile ->
                    val target = File(modelDirectory(), modelFile.name)
                    val request = DownloadManager.Request(Uri.parse(modelFile.url))
                        .setTitle("Nemotron · ${modelFile.name}")
                        .setDescription("实时字幕")
                        .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
                        .setDestinationUri(Uri.fromFile(target))
                        .setAllowedOverRoaming(false)
                    preferences.edit()
                        .putLong(downloadKey(modelFile), downloadManager.enqueue(request))
                        .apply()
                }
            }.onSuccess {
                mutableState.value = ModelState(ModelPhase.Downloading)
                monitorDownloads()
            }.onFailure {
                cleanupFailedDownload()
                mutableState.value = ModelState(ModelPhase.Error, detail = "无法开始下载")
            }
        }
    }

    private suspend fun monitorDownloads() {
        val ids = activeDownloadIds()
        if (ids.size != MODEL_FILES.size) {
            cleanupFailedDownload()
            mutableState.value = ModelState(ModelPhase.Error, detail = "下载已中断，请重试")
            return
        }
        while (scope.isActive) {
            var downloadedBytes = 0L
            var allFinished = true
            for ((modelFile, id) in ids) {
                val result = queryDownload(id)
                if (result == null || result.status == DownloadManager.STATUS_FAILED) {
                    cleanupFailedDownload()
                    mutableState.value = ModelState(ModelPhase.Error, detail = "下载失败，请重试")
                    return
                }
                allFinished = allFinished && result.status == DownloadManager.STATUS_SUCCESSFUL
                downloadedBytes += if (result.status == DownloadManager.STATUS_SUCCESSFUL) {
                    modelFile.size
                } else {
                    result.downloadedBytes.coerceAtLeast(0L).coerceAtMost(modelFile.size)
                }
            }
            val progress = ((downloadedBytes * 100) / TOTAL_SIZE).toInt().coerceIn(0, 100)
            mutableState.value = ModelState(ModelPhase.Downloading, progressPercent = progress)
            if (allFinished) {
                verifyDownloads()
                return
            }
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

    private fun verifyDownloads() {
        mutableState.value = ModelState(ModelPhase.Preparing)
        runCatching {
            MODEL_FILES.forEachIndexed { index, modelFile ->
                val file = File(modelDirectory(), modelFile.name)
                require(file.length() == modelFile.size) { "${modelFile.name} 大小不正确" }
                require(file.sha256() == modelFile.sha256) { "${modelFile.name} 校验失败" }
                mutableState.value = ModelState(
                    ModelPhase.Preparing,
                    progressPercent = ((index + 1) * 100) / MODEL_FILES.size,
                )
            }
            readyMarker().writeText(MODEL_REVISION)
            clearDownloadIds()
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

    fun modelDirectory(): File = File(
        requireNotNull(appContext.getExternalFilesDir(null)),
        "models/$MODEL_NAME",
    )

    private fun hasReadyMarker(): Boolean =
        readyMarker().takeIf(File::isFile)?.readText() == MODEL_REVISION &&
            MODEL_FILES.all { File(modelDirectory(), it.name).length() == it.size }

    private fun allModelFilesExist(): Boolean = MODEL_FILES.all {
        File(modelDirectory(), it.name).isFile
    }

    private fun readyMarker(): File = File(modelDirectory(), ".ready")

    private fun activeDownloadIds(): Map<ModelFile, Long> = MODEL_FILES.mapNotNull { modelFile ->
        preferences.takeIf { it.contains(downloadKey(modelFile)) }
            ?.getLong(downloadKey(modelFile), -1L)
            ?.takeIf { it >= 0L }
            ?.let { modelFile to it }
    }.toMap()

    private fun cleanupFailedDownload() {
        val ids = activeDownloadIds().values.toLongArray()
        if (ids.isNotEmpty()) downloadManager.remove(*ids)
        clearDownloadIds()
        modelDirectory().deleteRecursively()
    }

    private fun clearDownloadIds() {
        preferences.edit().also { editor ->
            MODEL_FILES.forEach { editor.remove(downloadKey(it)) }
        }.apply()
    }

    private fun cleanupLegacyArchive() {
        File(appContext.filesDir, "models/$MODEL_NAME.partial").deleteRecursively()
        File(
            appContext.getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS),
            "$MODEL_NAME.tar.bz2",
        ).delete()
        preferences.edit().remove("nemotron_download_id").apply()
    }

    private fun downloadKey(modelFile: ModelFile): String = "download_${modelFile.name}"

    override fun close() {
        scope.cancel()
    }

    private data class DownloadResult(val status: Int, val downloadedBytes: Long)
    private data class ModelFile(val name: String, val size: Long, val sha256: String) {
        val url: String
            get() = "$MODEL_BASE_URL/$name?download=true"
    }

    private companion object {
        const val PREFERENCES = "captions_model_downloads"
        const val POLL_INTERVAL_MILLIS = 750L
        const val MODEL_NAME =
            "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25"
        const val MODEL_REVISION = "52056fdc070914a48dcd68b31b44d6a6f5b85902"
        const val MODEL_BASE_URL = "https://huggingface.co/csukuangfj2/$MODEL_NAME/resolve/$MODEL_REVISION"
        val MODEL_FILES = listOf(
            ModelFile(
                "encoder.int8.onnx",
                652_916_849L,
                "7d932213491ad355c6e5576705dc3494731a52af87d7a1b954559340147909d8",
            ),
            ModelFile(
                "decoder.int8.onnx",
                7_257_753L,
                "0be9702c2f427a2b6bb241d298e0d3836a558de1f5b9fd3018f1cce6e2b3fa98",
            ),
            ModelFile(
                "joiner.int8.onnx",
                1_735_862L,
                "a35eac38a22ebceb04d230ed7afe0d68f446ba6914a036b97f14fece95967e23",
            ),
            ModelFile(
                "tokens.txt",
                8_952L,
                "dc0b4584ab2e4ddbf888425c076c61b736e7356a015250db7d307e6f1a8188ff",
            ),
        )
        val TOTAL_SIZE = MODEL_FILES.sumOf(ModelFile::size)
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
