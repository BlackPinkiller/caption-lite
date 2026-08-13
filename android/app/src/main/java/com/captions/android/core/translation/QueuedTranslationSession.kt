package com.captions.android.core.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationSession
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

class QueuedTranslationSession(
    private val translator: TextTranslator,
) : TranslationSession {
    private val generation = AtomicLong(0)
    private val executor = ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        ArrayBlockingQueue(QUEUE_CAPACITY),
        { task -> Thread(task, "captions-translation").apply { isDaemon = true } },
        ThreadPoolExecutor.AbortPolicy(),
    )

    override fun submit(
        cueId: Long,
        text: String,
        settings: TranslationSettings,
        onResult: (Long, String) -> Unit,
        onError: (String) -> Unit,
    ): Boolean {
        if (!settings.enabled || text.isBlank()) return false
        val currentGeneration = generation.get()
        return runCatching {
            executor.execute {
                if (currentGeneration != generation.get()) return@execute
                runCatching { translator.translate(text.trim(), settings) }
                    .onSuccess { translated ->
                        if (currentGeneration == generation.get() && translated.isNotBlank()) {
                            onResult(cueId, translated.trim())
                        }
                    }
                    .onFailure { error ->
                        if (currentGeneration == generation.get()) {
                            onError(error.message ?: "翻译失败")
                        }
                    }
            }
        }.isSuccess
    }

    override fun cancelPending() {
        generation.incrementAndGet()
        executor.queue.clear()
    }

    override fun close() {
        cancelPending()
        executor.shutdownNow()
    }

    private companion object {
        const val QUEUE_CAPACITY = 24
    }
}
