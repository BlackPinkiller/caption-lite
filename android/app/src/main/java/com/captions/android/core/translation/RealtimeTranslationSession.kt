package com.captions.android.core.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput
import com.captions.android.ports.TranslationSession
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

class RealtimeTranslationSession(
    private val translator: TextTranslator,
) : TranslationSession {
    private val generation = AtomicLong(0)
    private val cueVersions = ConcurrentHashMap<Long, AtomicLong>()
    private val previewExecutor = worker("captions-translation-preview", PREVIEW_QUEUE_CAPACITY)
    private val finalExecutor = worker("captions-translation-final", FINAL_QUEUE_CAPACITY)
    private val scheduler = Executors.newSingleThreadScheduledExecutor { task ->
        Thread(task, "captions-translation-schedule").apply { isDaemon = true }
    }
    private val previewLock = Any()
    private var activeCueId = -1L
    private var lastPreviewText = ""
    private var lastPreviewSentAt = 0L
    private var pendingPreview: Request? = null
    private var scheduledPreview: ScheduledFuture<*>? = null

    override fun preview(
        cueId: Long,
        text: String,
        context: List<String>,
        settings: TranslationSettings,
        onResult: (Long, String) -> Unit,
    ): Boolean {
        val source = text.trim()
        if (!settings.enabled || source.length < PREVIEW_MIN_CHARS) return false
        val request = Request(cueId, source, context.toList(), settings, onResult)
        return runCatching {
            synchronized(previewLock) {
                if (activeCueId != cueId) resetPreviewLocked(cueId)
                pendingPreview = request
                if (source == lastPreviewText) return@synchronized
                val elapsedMillis = if (lastPreviewSentAt == 0L) {
                    PREVIEW_INTERVAL_MILLIS
                } else {
                    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - lastPreviewSentAt)
                }
                val changed = changedCharacters(lastPreviewText, source)
                val delay = if (
                    lastPreviewText.isEmpty() ||
                    changed >= PREVIEW_CHAR_DELTA ||
                    elapsedMillis >= PREVIEW_INTERVAL_MILLIS
                ) {
                    0L
                } else {
                    PREVIEW_INTERVAL_MILLIS - elapsedMillis
                }
                scheduledPreview?.cancel(false)
                scheduledPreview = scheduler.schedule(::sendPendingPreview, delay, TimeUnit.MILLISECONDS)
            }
        }.isSuccess
    }

    override fun commit(
        cueId: Long,
        text: String,
        context: List<String>,
        settings: TranslationSettings,
        onResult: (Long, String) -> Unit,
        onError: (String) -> Unit,
    ): Boolean {
        val source = text.trim()
        if (!settings.enabled || source.isEmpty()) return false
        synchronized(previewLock) {
            if (activeCueId == cueId) {
                scheduledPreview?.cancel(false)
                scheduledPreview = null
                pendingPreview = null
            }
        }
        val currentGeneration = generation.get()
        val version = nextVersion(cueId)
        val submittedAt = System.nanoTime()
        return runCatching {
            finalExecutor.execute {
                val ageMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - submittedAt)
                if (ageMillis > settings.timeoutMillis) {
                    if (isCurrent(cueId, version, currentGeneration)) {
                        onError("翻译等待超时")
                    }
                    return@execute
                }
                translate(
                    request = Request(cueId, source, context.toList(), settings, onResult),
                    version = version,
                    currentGeneration = currentGeneration,
                    onError = onError,
                )
            }
        }.isSuccess
    }

    private fun sendPendingPreview() {
        val request = synchronized(previewLock) {
            val current = pendingPreview ?: return
            pendingPreview = null
            scheduledPreview = null
            if (current.text == lastPreviewText) return
            lastPreviewText = current.text
            lastPreviewSentAt = System.nanoTime()
            current
        }
        val currentGeneration = generation.get()
        val version = nextVersion(request.cueId)
        previewExecutor.queue.clear()
        runCatching {
            previewExecutor.execute {
                translate(
                    request = request,
                    version = version,
                    currentGeneration = currentGeneration,
                    onError = null,
                )
            }
        }
    }

    private fun translate(
        request: Request,
        version: Long,
        currentGeneration: Long,
        onError: ((String) -> Unit)?,
    ) {
        if (!isCurrent(request.cueId, version, currentGeneration)) return
        runCatching {
            translator.translate(
                TranslationInput(request.text, request.context),
                request.settings,
            )
        }.onSuccess { translated ->
            if (
                translated.isNotBlank() &&
                isCurrent(request.cueId, version, currentGeneration)
            ) {
                request.onResult(request.cueId, translated.trim())
            }
        }.onFailure { error ->
            if (onError != null && isCurrent(request.cueId, version, currentGeneration)) {
                onError(error.message ?: "翻译失败")
            }
        }
    }

    override fun cancelPending() {
        generation.incrementAndGet()
        cueVersions.clear()
        previewExecutor.queue.clear()
        finalExecutor.queue.clear()
        synchronized(previewLock) {
            scheduledPreview?.cancel(false)
            resetPreviewLocked(-1L)
        }
    }

    override fun close() {
        cancelPending()
        scheduler.shutdownNow()
        previewExecutor.shutdownNow()
        finalExecutor.shutdownNow()
        translator.close()
    }

    private fun resetPreviewLocked(cueId: Long) {
        scheduledPreview?.cancel(false)
        scheduledPreview = null
        pendingPreview = null
        activeCueId = cueId
        lastPreviewText = ""
        lastPreviewSentAt = 0L
    }

    private fun nextVersion(cueId: Long): Long =
        cueVersions.computeIfAbsent(cueId) { AtomicLong(0) }.incrementAndGet()

    private fun isCurrent(cueId: Long, version: Long, currentGeneration: Long): Boolean =
        generation.get() == currentGeneration && cueVersions[cueId]?.get() == version

    private fun changedCharacters(previous: String, current: String): Int {
        val common = previous.zip(current).indexOfFirst { (old, new) -> old != new }
            .let { if (it < 0) minOf(previous.length, current.length) else it }
        return max(previous.length, current.length) - common
    }

    private fun worker(name: String, capacity: Int) = ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        ArrayBlockingQueue(capacity),
        { task -> Thread(task, name).apply { isDaemon = true } },
        ThreadPoolExecutor.AbortPolicy(),
    )

    private data class Request(
        val cueId: Long,
        val text: String,
        val context: List<String>,
        val settings: TranslationSettings,
        val onResult: (Long, String) -> Unit,
    )

    private companion object {
        const val PREVIEW_MIN_CHARS = 4
        const val PREVIEW_INTERVAL_MILLIS = 600L
        const val PREVIEW_CHAR_DELTA = 18
        const val PREVIEW_QUEUE_CAPACITY = 1
        const val FINAL_QUEUE_CAPACITY = 24
    }
}
