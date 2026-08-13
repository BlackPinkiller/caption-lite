package com.captions.android.core.translation

import com.captions.android.core.session.TranslationSettings
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class QueuedTranslationSessionTest {
    @Test
    fun translatesACommittedCueOnTheWorker() {
        val caller = Thread.currentThread()
        var worker: Thread? = null
        val completed = CountDownLatch(1)
        var result = ""
        val session = QueuedTranslationSession { input, _ ->
            worker = Thread.currentThread()
            "译文：${input.text}"
        }

        assertTrue(
            session.submit(
                cueId = 7,
                text = "source",
                context = listOf("earlier"),
                settings = TranslationSettings(),
                onResult = { cueId, text ->
                    result = "$cueId:$text"
                    completed.countDown()
                },
                onError = { throw AssertionError(it) },
            ),
        )

        assertTrue(completed.await(2, TimeUnit.SECONDS))
        assertTrue(worker !== caller)
        assertEquals("7:译文：source", result)
        session.close()
    }

    @Test
    fun disabledTranslationIsNotQueued() {
        val session = QueuedTranslationSession { _, _ -> error("must not run") }

        val accepted = session.submit(
            cueId = 1,
            text = "source",
            context = emptyList(),
            settings = TranslationSettings(enabled = false),
            onResult = { _, _ -> },
            onError = {},
        )

        assertEquals(false, accepted)
        session.close()
    }
}
