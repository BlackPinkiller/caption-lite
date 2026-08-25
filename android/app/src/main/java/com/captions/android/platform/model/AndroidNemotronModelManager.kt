package com.captions.android.platform.model

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import com.captions.android.core.session.NemotronModel
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
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class AndroidNemotronModelManager(
    context: Context,
    initialModel: NemotronModel = NemotronModel.English560Ms,
) : RecognitionModelManager {
    private val appContext = context.applicationContext
    private val downloadManager = appContext.getSystemService(DownloadManager::class.java)
    private val preferences = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutableState = MutableStateFlow(ModelState(ModelPhase.Missing))
    private var monitorJob: Job? = null
    private var selectedModel = initialModel

    override val state: StateFlow<ModelState> = mutableState.asStateFlow()

    fun configure(model: NemotronModel) {
        if (selectedModel == model) return
        selectedModel = model
        mutableState.value = ModelState(ModelPhase.Missing)
        refresh()
    }

    init {
        refresh()
    }

    override fun refresh() {
        monitorJob?.cancel()
        val spec = modelSpec()
        monitorJob = scope.launch {
            cleanupLegacyArchive()
            when {
                hasReadyMarker(spec) -> mutableState.value = ModelState(ModelPhase.Ready)
                activeDownloadIds(spec).isNotEmpty() -> monitorDownloads(spec)
                allModelFilesExist(spec) -> verifyDownloads(spec)
                else -> mutableState.value = ModelState(ModelPhase.Missing)
            }
        }
    }

    override fun download() {
        if (state.value.phase in setOf(ModelPhase.Downloading, ModelPhase.Preparing, ModelPhase.Ready)) {
            return
        }
        monitorJob?.cancel()
        val spec = modelSpec()
        monitorJob = scope.launch {
            runCatching {
                cleanupFailedDownload(spec)
                modelDirectory(spec).mkdirs()
                spec.files.forEach { modelFile ->
                    val target = File(modelDirectory(spec), modelFile.name)
                    val request = DownloadManager.Request(Uri.parse(spec.url(modelFile)))
                        .setTitle("Nemotron ${spec.label} · ${modelFile.name}")
                        .setDescription("实时字幕")
                        .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
                        .setDestinationUri(Uri.fromFile(target))
                        .setAllowedOverRoaming(false)
                    preferences.edit()
                        .putLong(downloadKey(spec, modelFile), downloadManager.enqueue(request))
                        .apply()
                }
            }.onSuccess {
                mutableState.value = ModelState(ModelPhase.Downloading)
                monitorDownloads(spec)
            }.onFailure {
                cleanupFailedDownload(spec)
                mutableState.value = ModelState(ModelPhase.Error, detail = "无法开始下载")
            }
        }
    }

    private suspend fun monitorDownloads(spec: ModelSpec) {
        val ids = activeDownloadIds(spec)
        if (ids.size != spec.files.size) {
            cleanupFailedDownload(spec)
            mutableState.value = ModelState(ModelPhase.Error, detail = "下载已中断，请重试")
            return
        }
        while (currentCoroutineContext().isActive) {
            var downloadedBytes = 0L
            var allFinished = true
            for ((modelFile, id) in ids) {
                val result = queryDownload(id)
                if (result == null || result.status == DownloadManager.STATUS_FAILED) {
                    cleanupFailedDownload(spec)
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
            val progress = ((downloadedBytes * 100) / spec.totalSize).toInt().coerceIn(0, 100)
            mutableState.value = ModelState(ModelPhase.Downloading, progressPercent = progress)
            if (allFinished) {
                verifyDownloads(spec)
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

    private fun verifyDownloads(spec: ModelSpec) {
        mutableState.value = ModelState(ModelPhase.Preparing)
        runCatching {
            spec.files.forEachIndexed { index, modelFile ->
                val file = File(modelDirectory(spec), modelFile.name)
                require(file.length() == modelFile.size) { "${modelFile.name} 大小不正确" }
                require(file.sha256() == modelFile.sha256) { "${modelFile.name} 校验失败" }
                mutableState.value = ModelState(
                    ModelPhase.Preparing,
                    progressPercent = ((index + 1) * 100) / spec.files.size,
                )
            }
            readyMarker(spec).writeText(spec.revision)
            clearDownloadIds(spec)
        }.onSuccess {
            mutableState.value = ModelState(ModelPhase.Ready)
        }.onFailure { error ->
            cleanupFailedDownload(spec)
            mutableState.value = ModelState(
                ModelPhase.Error,
                detail = error.message ?: "模型准备失败",
            )
        }
    }

    fun modelDirectory(): File = modelDirectory(modelSpec())

    private fun modelDirectory(spec: ModelSpec): File = File(
        requireNotNull(appContext.getExternalFilesDir(null)),
        "models/${spec.name}",
    )

    private fun hasReadyMarker(spec: ModelSpec): Boolean =
        readyMarker(spec).takeIf(File::isFile)?.readText() == spec.revision &&
            spec.files.all { File(modelDirectory(spec), it.name).length() == it.size }

    private fun allModelFilesExist(spec: ModelSpec): Boolean = spec.files.all {
        File(modelDirectory(spec), it.name).isFile
    }

    private fun readyMarker(spec: ModelSpec): File = File(modelDirectory(spec), ".ready")

    private fun activeDownloadIds(spec: ModelSpec): Map<ModelFile, Long> = spec.files.mapNotNull { modelFile ->
        preferences.takeIf { it.contains(downloadKey(spec, modelFile)) }
            ?.getLong(downloadKey(spec, modelFile), -1L)
            ?.takeIf { it >= 0L }
            ?.let { modelFile to it }
    }.toMap()

    private fun cleanupFailedDownload(spec: ModelSpec) {
        val ids = activeDownloadIds(spec).values.toLongArray()
        if (ids.isNotEmpty()) downloadManager.remove(*ids)
        clearDownloadIds(spec)
        modelDirectory(spec).deleteRecursively()
    }

    private fun clearDownloadIds(spec: ModelSpec) {
        preferences.edit().also { editor ->
            spec.files.forEach { editor.remove(downloadKey(spec, it)) }
        }.apply()
    }

    private fun cleanupLegacyArchive() {
        File(appContext.filesDir, "models/${ENGLISH_560.name}.partial").deleteRecursively()
        File(
            appContext.getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS),
            "${ENGLISH_560.name}.tar.bz2",
        ).delete()
        preferences.edit().remove("nemotron_download_id").apply()
    }

    private fun downloadKey(spec: ModelSpec, modelFile: ModelFile): String =
        "download_${spec.name}_${modelFile.name}"

    private fun modelSpec(): ModelSpec = when (selectedModel) {
        NemotronModel.English560Ms -> ENGLISH_560
        NemotronModel.English1120Ms -> ENGLISH_1120
    }

    override fun close() {
        scope.cancel()
    }

    private data class DownloadResult(val status: Int, val downloadedBytes: Long)
    private data class ModelFile(val name: String, val size: Long, val sha256: String)

    private data class ModelSpec(
        val label: String,
        val name: String,
        val revision: String,
        val files: List<ModelFile>,
    ) {
        val baseUrl: String
            get() = "https://huggingface.co/csukuangfj2/$name/resolve/$revision"
        val totalSize: Long = files.sumOf(ModelFile::size)
        fun url(file: ModelFile): String = "$baseUrl/${file.name}?download=true"
    }

    private companion object {
        const val PREFERENCES = "captions_model_downloads"
        const val POLL_INTERVAL_MILLIS = 750L
        val COMMON_FILES = listOf(
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
        val ENGLISH_560 = ModelSpec(
            label = "560 ms",
            name = "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25",
            revision = "52056fdc070914a48dcd68b31b44d6a6f5b85902",
            files = listOf(
                ModelFile(
                    "encoder.int8.onnx",
                    652_916_849L,
                    "7d932213491ad355c6e5576705dc3494731a52af87d7a1b954559340147909d8",
                ),
            ) + COMMON_FILES,
        )
        val ENGLISH_1120 = ModelSpec(
            label = "1120 ms",
            name = "sherpa-onnx-nemotron-speech-streaming-en-0.6b-1120ms-int8-2026-04-25",
            revision = "b0b6bae3da99ea3d81b315ba018e951501850c2c",
            files = listOf(
                ModelFile(
                    "encoder.int8.onnx",
                    652_916_852L,
                    "7d2246da3c077e8b57698d398e09d8ca67f50de73b3468af397b22213ce72117",
                ),
            ) + COMMON_FILES,
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
