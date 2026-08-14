package com.captions.android.core.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RealtimeTranslationSessionTest {
    @Test
    fun translatesPreviewOffTheCallerThread() {
        val caller = Thread.currentThread()
        var worker: Thread? = null
        val completed = CountDownLatch(1)
        var result = ""
        val session = RealtimeTranslationSession { input, _ ->
            worker = Thread.currentThread()
            "译文：${input.text}"
        }

        assertTrue(
            session.preview(
                cueId = 7,
                text = "source",
                context = listOf("earlier"),
                settings = TranslationSettings(),
                onResult = { cueId, text ->
                    result = "$cueId:$text"
                    completed.countDown()
                },
            ),
        )

        assertTrue(completed.await(2, TimeUnit.SECONDS))
        assertTrue(worker !== caller)
        assertEquals("7:译文：source", result)
        session.close()
    }

    @Test
    fun finalResultCannotBeOverwrittenByAnOlderPreview() {
        val previewStarted = CountDownLatch(1)
        val releasePreview = CountDownLatch(1)
        val finalCompleted = CountDownLatch(1)
        val results = mutableListOf<String>()
        val session = RealtimeTranslationSession { input, _ ->
            if (input.text == "partial source") {
                previewStarted.countDown()
                releasePreview.await(2, TimeUnit.SECONDS)
                "旧预览"
            } else {
                "最终译文"
            }
        }

        session.preview(
            cueId = 1,
            text = "partial source",
            context = emptyList(),
            settings = TranslationSettings(),
            onResult = { _, text -> synchronized(results) { results += text } },
        )
        assertTrue(previewStarted.await(2, TimeUnit.SECONDS))
        session.commit(
            cueId = 1,
            text = "final source",
            context = emptyList(),
            settings = TranslationSettings(),
            onResult = { _, text ->
                synchronized(results) { results += text }
                finalCompleted.countDown()
            },
            onError = { throw AssertionError(it) },
        )

        assertTrue(finalCompleted.await(2, TimeUnit.SECONDS))
        releasePreview.countDown()
        Thread.sleep(100)
        assertEquals(listOf("最终译文"), synchronized(results) { results.toList() })
        session.close()
    }

    @Test
    fun disabledTranslationIsNotQueued() {
        val session = RealtimeTranslationSession { _, _ -> error("must not run") }

        val accepted = session.commit(
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

    @Test
    fun closeReleasesTranslatorResources() {
        var closed = false
        val translator = object : TextTranslator {
            override fun translate(
                input: TranslationInput,
                settings: TranslationSettings,
            ): String = input.text

            override fun close() {
                closed = true
            }
        }
        val session = RealtimeTranslationSession(translator)

        session.close()

        assertTrue(closed)
    }
}
