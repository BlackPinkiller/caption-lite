package com.captions.android.core.recognition

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RecognitionSegmenterTest {
    @Test
    fun `terminal punctuation requires a followup update`() {
        var now = 1_000L
        val segmenter = RecognitionSegmenter(nowMillis = { now })

        val first = segmenter.update("Hello world.")
        now = 1_560L
        val second = segmenter.update("Hello world.")

        assertTrue(first.committed.isEmpty())
        assertEquals("Hello world.", second.committed)
    }

    @Test
    fun `following text remains active after punctuation commit`() {
        val segmenter = RecognitionSegmenter(nowMillis = { 1_000L })
        segmenter.update("One.")

        val update = segmenter.update("One. Two")

        assertEquals("One.", update.committed)
        assertEquals("Two", update.active)
    }

    @Test
    fun `long text is forced at a word boundary`() {
        val segmenter = RecognitionSegmenter(
            maxChars = 20,
            splitLookbackChars = 4,
            splitLookaheadChars = 5,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("one two three four five six")

        assertTrue(update.forced)
        assertTrue(update.committed.isNotEmpty())
        assertFalse(update.committed.endsWith(" f"))
    }

    @Test
    fun `soft limit waits for forward punctuation`() {
        val segmenter = RecognitionSegmenter(
            maxChars = 20,
            splitLookbackChars = 4,
            splitLookaheadChars = 20,
            nowMillis = { 1_000L },
        )

        val waiting = segmenter.update("one two three four five six")
        val committed = segmenter.update("one two three four five six seven.")

        assertTrue(waiting.committed.isEmpty())
        assertEquals("one two three four five six seven.", committed.committed)
        assertFalse(committed.forced)
    }

    @Test
    fun `consumed position only moves forward across repeated cumulative text`() {
        val segmenter = RecognitionSegmenter(
            maxChars = 24,
            splitLookbackChars = 4,
            splitLookaheadChars = 8,
            nowMillis = { 1_000L },
        )
        val text = "repeat this phrase ".repeat(8)
        segmenter.update(text)
        val lengths = mutableListOf(segmenter.active.length)
        val hardLimit = segmenter.maxChars + segmenter.splitLookaheadChars

        while (segmenter.active.length >= hardLimit) {
            segmenter.update(text)
            lengths += segmenter.active.length
        }

        assertEquals(lengths.sortedDescending(), lengths)
    }

    @Test
    fun `time limit commits the whole active text`() {
        var now = 1_000L
        val segmenter = RecognitionSegmenter(
            maxChars = 240,
            maxDurationMillis = 10_000L,
            nowMillis = { now },
        )
        segmenter.update("one sentence is still being spoken")
        now = 11_000L

        val update = segmenter.update("one sentence is still being spoken very slowly")

        assertEquals("one sentence is still being spoken very slowly", update.committed)
        assertEquals("", update.active)
    }

    @Test
    fun `minor revision after a forced commit keeps the consumed boundary`() {
        var now = 1_000L
        val segmenter = RecognitionSegmenter(
            maxChars = 500,
            maxDurationMillis = 10_000L,
            nowMillis = { now },
        )
        val original =
            "recognition continues while each phrase had fresh material and avoids repetition"
        segmenter.update(original)
        now = 11_000L
        assertEquals(original, segmenter.update(original).committed)
        now = 12_000L

        val revised = segmenter.update(
            "recognition continues while each phrase adds fresh material and avoids repetition " +
                "before the next idea",
        )

        assertTrue(revised.committed.isEmpty())
        assertEquals("before the next idea", revised.active)
    }

    @Test
    fun `unrelated cumulative text still starts a new segment`() {
        var now = 1_000L
        val segmenter = RecognitionSegmenter(
            maxChars = 500,
            maxDurationMillis = 10_000L,
            nowMillis = { now },
        )
        val original = "the first recognition stream contains a long completed thought"
        segmenter.update(original)
        now = 11_000L
        segmenter.update(original)
        now = 12_000L

        val replacement = segmenter.update("a completely unrelated new recognition stream")

        assertEquals("a completely unrelated new recognition stream", replacement.active)
    }

    @Test
    fun `chinese punctuation can split continuous text`() {
        val segmenter = RecognitionSegmenter(
            maxChars = 4,
            splitLookbackChars = 1,
            splitLookaheadChars = 8,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("这是第一句。这是第二句")

        assertEquals("这是第一句。", update.committed)
        assertEquals("这是第二句", update.active)
        assertFalse(update.forced)
    }
}
