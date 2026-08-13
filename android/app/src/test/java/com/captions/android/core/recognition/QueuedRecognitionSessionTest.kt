package com.captions.android.core.recognition

import com.captions.android.ports.RecognitionUpdate
import com.captions.android.ports.StreamingRecognizer
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class QueuedRecognitionSessionTest {
    @Test
    fun decodesOffTheCallerAndResetsAtAnEndpoint() {
        val recognizer = FakeRecognizer()
        val ready = CountDownLatch(1)
        val updated = CountDownLatch(1)
        val session = QueuedRecognitionSession { recognizer }

        session.start(
            onReady = ready::countDown,
            onUpdate = { updated.countDown() },
            onError = { throw AssertionError(it) },
        )
        assertTrue(ready.await(2, TimeUnit.SECONDS))
        assertTrue(session.accept(shortArrayOf(1, 2, 3)))
        assertTrue(updated.await(2, TimeUnit.SECONDS))

        session.close()
        assertEquals(1, recognizer.acceptCount)
        assertEquals(2, recognizer.resetCount)
    }

    @Test
    fun immediateRestartCannotReuseTheOldRun() {
        val allowCreation = CountDownLatch(1)
        val newRunReady = CountDownLatch(1)
        val recognizer = FakeRecognizer()
        val session = QueuedRecognitionSession {
            allowCreation.await(2, TimeUnit.SECONDS)
            recognizer
        }
        var oldReadyCount = 0

        session.start(
            onReady = { oldReadyCount += 1 },
            onUpdate = {},
            onError = { throw AssertionError(it) },
        )
        session.stop()
        session.start(
            onReady = newRunReady::countDown,
            onUpdate = {},
            onError = { throw AssertionError(it) },
        )
        allowCreation.countDown()

        assertTrue(newRunReady.await(2, TimeUnit.SECONDS))
        assertEquals(0, oldReadyCount)
        assertEquals(2, recognizer.resetCount)
        session.close()
    }

    private class FakeRecognizer : StreamingRecognizer {
        var acceptCount = 0
        var resetCount = 0

        override fun reset() {
            resetCount += 1
        }

        override fun accept(samples: ShortArray): RecognitionUpdate {
            acceptCount += 1
            return RecognitionUpdate("recognized", endpoint = true)
        }

        override fun close() = Unit
    }
}
