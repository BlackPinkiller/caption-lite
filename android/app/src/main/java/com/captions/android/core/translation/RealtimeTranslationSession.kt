package com.captions.android.core.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.session.sourceExtendsTranslation
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
    private val versionSequence = AtomicLong(0)
    private val cueVersions = ConcurrentHashMap<Long, Long>()
    private val previewExecutor = worker("captions-translation-preview", PREVIEW_QUEUE_CAPACITY)
    private val finalExecutor = worker("captions-translation-final", FINAL_QUEUE_CAPACITY)
    private val scheduler = Executors.newSingleThreadScheduledExecutor { task ->
        Thread(task, "captions-translation-schedule").apply { isDaemon = true }
    }
    private val previewLock = Any()
    private var activeCueId = -1L
    private var lastPreviewRequest: Request? = null
    private val lastPreviewText: String get() = lastPreviewRequest?.text.orEmpty()
    private var lastPreviewSentAt = 0L
    private var pendingPreview: Request? = null
    private var scheduledPreview: ScheduledFuture<*>? = null
    private var latestPreview: Request? = null
    private var completedPreview: CompletedPreview? = null
    private var previewInFlight = false
    private var closed = false

    override fun preview(
        cueId: Long,
        text: String,
        context: List<String>,
        settings: TranslationSettings,
        onResult: (Long, String) -> Unit,
    ): Boolean {
        val source = text.trim()
        val request = Request(cueId, source, context.toList(), settings, onResult)
        return runCatching {
            synchronized(previewLock) {
                check(!closed)
                if (activeCueId != cueId) resetPreviewLocked(cueId)
                if (!request.hasSameInput(completedPreview?.request)) completedPreview = null
                latestPreview = request
                val eligible = settings.enabled && source.length >= PREVIEW_MIN_CHARS
                pendingPreview = request.takeIf { eligible && !it.hasSameInput(lastPreviewRequest) }
                schedulePreviewLocked()
                eligible
            }
        }.getOrDefault(false)
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
        return synchronized(previewLock) {
            if (closed) return false
            if (activeCueId == cueId) {
                scheduledPreview?.cancel(false)
                scheduledPreview = null
                pendingPreview = null
                latestPreview = null
            }
            val currentGeneration = generation.get()
            val version = nextVersion(cueId)
            val request = Request(cueId, source, context.toList(), settings, onResult)
            val cached = completedPreview?.takeIf { request.hasSameInput(it.request) }
            completedPreview = null
            val submittedAt = System.nanoTime()
            val accepted = runCatching {
                finalExecutor.execute {
                    val ageMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - submittedAt)
                    if (ageMillis > settings.timeoutMillis) {
                        synchronized(previewLock) {
                            if (isCurrent(cueId, version, currentGeneration)) {
                                retireVersion(cueId, version)
                                onError("翻译等待超时")
                            }
                        }
                        return@execute
                    }
                    if (cached != null) {
                        synchronized(previewLock) {
                            if (isCurrent(cueId, version, currentGeneration)) {
                                retireVersion(cueId, version)
                                request.onResult(cueId, cached.translation)
                            }
                        }
                    } else {
                        translate(
                            request = request,
                            version = version,
                            currentGeneration = currentGeneration,
                            onError = onError,
                        )
                    }
                }
            }.isSuccess
            if (!accepted) retireVersion(cueId, version)
            accepted
        }
    }

    private fun schedulePreviewLocked() {
        scheduledPreview?.cancel(false)
        scheduledPreview = null
        val request = pendingPreview ?: return
        if (previewInFlight || closed) return
        val elapsedMillis = if (lastPreviewSentAt == 0L) {
            PREVIEW_INTERVAL_MILLIS
        } else {
            TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - lastPreviewSentAt)
        }
        val delay = if (
            lastPreviewText.isEmpty() ||
            changedCharacters(lastPreviewText, request.text) >= PREVIEW_CHAR_DELTA
        ) 0L else (PREVIEW_INTERVAL_MILLIS - elapsedMillis).coerceAtLeast(0L)
        scheduledPreview = scheduler.schedule(::sendPendingPreview, delay, TimeUnit.MILLISECONDS)
    }

    private fun sendPendingPreview(): Unit = synchronized(previewLock) {
        if (previewInFlight || closed) return
        val request = pendingPreview ?: return
        pendingPreview = null
        scheduledPreview = null
        lastPreviewRequest = request
        lastPreviewSentAt = System.nanoTime()
        previewInFlight = true
        val currentGeneration = generation.get()
        val version = nextVersion(request.cueId)
        val accepted = runCatching {
            previewExecutor.execute {
                try {
                    translate(
                        request = request,
                        version = version,
                        currentGeneration = currentGeneration,
                        onError = null,
                        preview = true,
                    )
                } finally {
                    synchronized(previewLock) {
                        previewInFlight = false
                        schedulePreviewLocked()
                    }
                }
            }
        }.isSuccess
        if (!accepted) {
            previewInFlight = false
            retireVersion(request.cueId, version)
        }
    }

    private fun translate(
        request: Request,
        version: Long,
        currentGeneration: Long,
        onError: ((String) -> Unit)?,
        preview: Boolean = false,
    ) {
        try {
            synchronized(previewLock) {
                if (!canDeliver(request, version, currentGeneration, preview)) return
            }
            runCatching {
                translator.translate(
                    TranslationInput(request.text, request.context),
                    request.settings,
                )
            }.onSuccess { translated ->
                synchronized(previewLock) {
                    if (
                        translated.isNotBlank() &&
                        canDeliver(request, version, currentGeneration, preview)
                    ) {
                        if (preview) completedPreview = CompletedPreview(request, translated.trim())
                        retireVersion(request.cueId, version)
                        request.onResult(request.cueId, translated.trim())
                    }
                }
            }.onFailure { error ->
                synchronized(previewLock) {
                    if (onError != null && isCurrent(request.cueId, version, currentGeneration)) {
                        retireVersion(request.cueId, version)
                        onError(error.message ?: "翻译失败")
                    }
                }
            }
        } finally {
            retireVersion(request.cueId, version)
        }
    }

    private fun canDeliver(
        request: Request,
        version: Long,
        currentGeneration: Long,
        preview: Boolean,
    ): Boolean {
        if (!isCurrent(request.cueId, version, currentGeneration)) return false
        if (!preview) return true
        val latest = latestPreview ?: return false
        // Appending speech may use the completed prefix translation. A corrected
        // hypothesis, different cue, or settings change must not revive stale text.
        return latest.cueId == request.cueId && sourceExtendsTranslation(request.text, latest.text) &&
            latest.settings == request.settings && latest.context == request.context
    }

    override fun cancelPending() = synchronized(previewLock) {
        generation.incrementAndGet()
        cueVersions.clear()
        finalExecutor.queue.clear()
        resetPreviewLocked(-1L)
    }

    override fun close() {
        synchronized(previewLock) { closed = true }
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
        latestPreview = null
        completedPreview = null
        activeCueId = cueId
        lastPreviewRequest = null
        lastPreviewSentAt = 0L
    }

    private fun nextVersion(cueId: Long): Long {
        val version = versionSequence.incrementAndGet()
        cueVersions.compute(cueId) { _, _ -> version }
        return version
    }

    private fun retireVersion(cueId: Long, version: Long) {
        cueVersions.computeIfPresent(cueId) { _, current ->
            if (current == version) null else current
        }
    }

    private fun isCurrent(cueId: Long, version: Long, currentGeneration: Long): Boolean =
        generation.get() == currentGeneration && cueVersions[cueId] == version

    internal fun trackedCueCount(): Int = cueVersions.size

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

    private data class CompletedPreview(val request: Request, val translation: String)

    private data class Request(
        val cueId: Long,
        val text: String,
        val context: List<String>,
        val settings: TranslationSettings,
        val onResult: (Long, String) -> Unit,
    ) {
        fun hasSameInput(other: Request?): Boolean = other != null &&
            cueId == other.cueId && text == other.text && context == other.context && settings == other.settings
    }

    private companion object {
        const val PREVIEW_MIN_CHARS = 4
        const val PREVIEW_INTERVAL_MILLIS = 600L
        const val PREVIEW_CHAR_DELTA = 18
        const val PREVIEW_QUEUE_CAPACITY = 1
        const val FINAL_QUEUE_CAPACITY = 24
    }
}
