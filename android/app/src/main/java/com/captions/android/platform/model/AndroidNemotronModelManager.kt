package com.captions.android.platform.model

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Environment
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState
import com.captions.android.ports.RecognitionModelManager
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
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
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream

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
            when {
                isReady() -> mutableState.value = ModelState(ModelPhase.Ready)
                preferences.contains(KEY_DOWNLOAD_ID) -> monitorDownload(
                    preferences.getLong(KEY_DOWNLOAD_ID, -1L),
                )
                archiveFile().isFile -> prepareArchive()
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
            val archive = archiveFile()
            archive.parentFile?.mkdirs()
            archive.delete()
            val request = DownloadManager.Request(Uri.parse(MODEL_URL))
                .setTitle("Nemotron 语音模型")
                .setDescription("实时字幕")
                .setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED,
                )
                .setDestinationUri(Uri.fromFile(archive))
                .setAllowedOverRoaming(false)
            val id = downloadManager.enqueue(request)
            preferences.edit().putLong(KEY_DOWNLOAD_ID, id).apply()
            mutableState.value = ModelState(ModelPhase.Downloading)
            monitorDownload(id)
        }
    }

    private suspend fun monitorDownload(id: Long) {
        if (id < 0) {
            clearDownload()
            mutableState.value = ModelState(ModelPhase.Missing)
            return
        }
        while (scope.isActive) {
            val result = queryDownload(id)
            when (result.status) {
                DownloadManager.STATUS_PENDING,
                DownloadManager.STATUS_PAUSED,
                DownloadManager.STATUS_RUNNING,
                -> mutableState.value = ModelState(
                    phase = ModelPhase.Downloading,
                    progressPercent = result.progressPercent,
                )

                DownloadManager.STATUS_SUCCESSFUL -> {
                    clearDownload()
                    prepareArchive()
                    return
                }

                DownloadManager.STATUS_FAILED -> {
                    clearDownload()
                    mutableState.value = ModelState(
                        ModelPhase.Error,
                        detail = "下载失败，请重试",
                    )
                    return
                }

                else -> {
                    clearDownload()
                    mutableState.value = ModelState(ModelPhase.Missing)
                    return
                }
            }
            delay(POLL_INTERVAL_MILLIS)
        }
    }

    private fun queryDownload(id: Long): DownloadResult {
        val query = DownloadManager.Query().setFilterById(id)
        downloadManager.query(query).use { cursor ->
            if (!cursor.moveToFirst()) return DownloadResult(DownloadManager.STATUS_FAILED, 0)
            val status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
            val downloaded = cursor.getLong(
                cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR),
            )
            val total = cursor.getLong(
                cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES),
            )
            val progress = if (total > 0) ((downloaded * 100) / total).toInt() else 0
            return DownloadResult(status, progress.coerceIn(0, 100))
        }
    }

    private fun prepareArchive() {
        mutableState.value = ModelState(ModelPhase.Preparing)
        runCatching {
            val archive = archiveFile()
            require(archive.length() == ARCHIVE_SIZE) { "模型文件大小不正确" }
            require(archive.sha256() == ARCHIVE_SHA256) { "模型文件校验失败" }

            val staging = File(modelParent(), "$MODEL_NAME.partial")
            staging.deleteRecursively()
            staging.mkdirs()
            extractTarBz2(archive, staging)

            val extracted = File(staging, MODEL_NAME)
            require(hasModelFiles(extracted)) { "模型文件不完整" }
            val target = modelDirectory()
            target.deleteRecursively()
            Files.move(
                extracted.toPath(),
                target.toPath(),
                StandardCopyOption.ATOMIC_MOVE,
            )
            staging.deleteRecursively()
            archive.delete()
        }.onSuccess {
            mutableState.value = ModelState(ModelPhase.Ready)
        }.onFailure { error ->
            mutableState.value = ModelState(
                ModelPhase.Error,
                detail = error.message ?: "模型准备失败",
            )
        }
    }

    private fun extractTarBz2(archive: File, destination: File) {
        val root = destination.canonicalFile
        FileInputStream(archive).use { fileInput ->
            BZip2CompressorInputStream(fileInput, true).use { compressed ->
                TarArchiveInputStream(compressed).use { tar ->
                    var entry = tar.nextEntry
                    while (entry != null) {
                        val output = File(root, entry.name).canonicalFile
                        require(output.path.startsWith(root.path + File.separator)) {
                            "模型压缩包包含非法路径"
                        }
                        if (entry.isDirectory) {
                            output.mkdirs()
                        } else {
                            output.parentFile?.mkdirs()
                            FileOutputStream(output).use { tar.copyTo(it) }
                        }
                        entry = tar.nextEntry
                    }
                }
            }
        }
    }

    fun modelDirectory(): File = File(modelParent(), MODEL_NAME)

    private fun modelParent(): File = File(appContext.filesDir, "models").apply { mkdirs() }

    private fun archiveFile(): File {
        val root = requireNotNull(appContext.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS))
        return File(root, "$MODEL_NAME.tar.bz2")
    }

    private fun isReady(): Boolean = hasModelFiles(modelDirectory())

    private fun hasModelFiles(directory: File): Boolean = MODEL_FILES.all {
        File(directory, it).isFile
    }

    private fun clearDownload() {
        preferences.edit().remove(KEY_DOWNLOAD_ID).apply()
    }

    override fun close() {
        scope.cancel()
    }

    private data class DownloadResult(val status: Int, val progressPercent: Int)

    private companion object {
        const val PREFERENCES = "captions_model_downloads"
        const val KEY_DOWNLOAD_ID = "nemotron_download_id"
        const val POLL_INTERVAL_MILLIS = 750L
        const val MODEL_NAME =
            "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25"
        const val MODEL_URL =
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$MODEL_NAME.tar.bz2"
        const val ARCHIVE_SIZE = 463_945_051L
        const val ARCHIVE_SHA256 =
            "78e2b79fcf7271553a74402a76b771b09ea40117a39566a79f52235b23db6358"
        val MODEL_FILES = listOf(
            "encoder.int8.onnx",
            "decoder.int8.onnx",
            "joiner.int8.onnx",
            "tokens.txt",
        )
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
