package com.captions.android.core.recognition

import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.SampleRecognitionSession
import com.captions.android.ports.StreamingRecognizer
import com.captions.android.ports.StreamingRecognizerFactory
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class QueuedRecognitionSession(
    private val factory: StreamingRecognizerFactory,
) : SampleRecognitionSession {
    private val active = AtomicBoolean(false)
    private val samples = ArrayBlockingQueue<ShortArray>(QUEUE_CAPACITY)
    private val executor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "captions-recognition").apply { isDaemon = true }
    }
    private var recognizer: StreamingRecognizer? = null

    override fun start(
        onReady: () -> Unit,
        onUpdate: (RecognitionUpdate) -> Unit,
        onError: (String) -> Unit,
    ) {
        if (!active.compareAndSet(false, true)) return
        samples.clear()
        executor.execute {
            try {
                val current = recognizer ?: factory.create().also { recognizer = it }
                current.reset()
                if (!active.get()) return@execute
                onReady()
                while (active.get()) {
                    val chunk = samples.poll(POLL_MILLIS, TimeUnit.MILLISECONDS) ?: continue
                    val update = current.accept(chunk)
                    if (update.endpoint) current.reset()
                    if (update.text.isNotEmpty() || update.endpoint) onUpdate(update)
                }
            } catch (error: Exception) {
                if (active.getAndSet(false)) {
                    onError(error.message ?: "语音识别失败")
                }
            } finally {
                samples.clear()
            }
        }
    }

    override fun accept(samples: ShortArray): Boolean {
        if (!active.get()) return false
        if (!this.samples.offer(samples)) {
            active.set(false)
            this.samples.clear()
            return false
        }
        return true
    }

    override fun stop() {
        active.set(false)
        samples.clear()
    }

    override fun close() {
        stop()
        executor.execute {
            recognizer?.close()
            recognizer = null
        }
        executor.shutdown()
    }

    private companion object {
        const val QUEUE_CAPACITY = 64
        const val POLL_MILLIS = 100L
    }
}
