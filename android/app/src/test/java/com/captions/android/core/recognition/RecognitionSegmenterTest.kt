package com.captions.android.core.recognition

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RecognitionSegmenterTest {
    @Test
    fun `trailing punctuation commits immediately`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("Hello world.")

        assertEquals(listOf("Hello world."), update.commits.map { it.text })
        assertEquals("", update.active)
        assertFalse(update.commits.first().forced)
    }

    @Test
    fun `mid text boundary commits and keeps the tail active`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("One. Two")

        assertEquals(listOf("One."), update.commits.map { it.text })
        assertEquals("Two", update.active)
    }

    @Test
    fun `multiple boundaries commit each sentence as its own cue`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("One. Two. Three")

        assertEquals(listOf("One.", "Two."), update.commits.map { it.text })
        assertEquals("Three", update.active)
    }

    @Test
    fun `short fragment below the floor stays active`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            minCommitChars = 4,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("ok.")

        assertEquals(emptyList<SegmentCommit>(), update.commits)
        assertEquals("ok.", update.active)
    }

    @Test
    fun `abbreviation period is not a boundary`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("Mr. Smith is here")

        assertEquals(emptyList<SegmentCommit>(), update.commits)
        assertEquals("Mr. Smith is here", update.active)
    }

    @Test
    fun `abbreviation followed by a later boundary skips the initial`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("Mr. Smith is here. Next")

        assertEquals(listOf("Mr. Smith is here."), update.commits.map { it.text })
        assertEquals("Next", update.active)
    }

    @Test
    fun `punctuation is disabled by default`() {
        val segmenter = RecognitionSegmenter(nowMillis = { 1_000L })

        val update = segmenter.update("Hello world. More")

        assertEquals(emptyList<SegmentCommit>(), update.commits)
        assertEquals("Hello world. More", update.active)
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

        assertTrue(update.commits.isNotEmpty())
        assertTrue(update.commits.last().forced)
        assertFalse(update.commits.last().text.endsWith(" f"))
    }

    @Test
    fun `soft limit waits for forward punctuation`() {
        val segmenter = RecognitionSegmenter(
            maxChars = 20,
            splitLookbackChars = 4,
            splitLookaheadChars = 20,
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val waiting = segmenter.update("one two three four five six")
        val committed = segmenter.update("one two three four five six seven.")

        assertTrue(waiting.commits.isEmpty())
        assertEquals(listOf("one two three four five six seven."), committed.commits.map { it.text })
        assertFalse(committed.commits.first().forced)
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

        assertEquals(
            listOf("one sentence is still being spoken very slowly"),
            update.commits.map { it.text },
        )
        assertEquals("", update.active)
    }

    @Test
    fun `flush commits the remaining active text`() {
        val segmenter = RecognitionSegmenter(nowMillis = { 1_000L })
        segmenter.update("one sentence")

        val update = segmenter.flush()

        assertEquals(listOf("one sentence"), update.commits.map { it.text })
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
        assertEquals(original, segmenter.update(original).commits.single().text)
        now = 12_000L

        val revised = segmenter.update(
            "recognition continues while each phrase adds fresh material and avoids repetition " +
                "before the next idea",
        )

        assertTrue(revised.commits.isEmpty())
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
    fun `short unrelated revision starts a new timer`() {
        var now = 1_000L
        val segmenter = RecognitionSegmenter(
            maxChars = 500,
            maxDurationMillis = 10_000L,
            nowMillis = { now },
        )
        segmenter.update("okay")
        now = 11_000L
        segmenter.update("okay")
        now = 22_000L

        val update = segmenter.update("nope")

        assertTrue(update.commits.isEmpty())
        assertEquals("nope", update.active)
    }

    @Test
    fun `chinese punctuation can split continuous text`() {
        val segmenter = RecognitionSegmenter(
            maxChars = 4,
            splitLookbackChars = 1,
            splitLookaheadChars = 8,
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("这是第一句。这是第二句")

        assertEquals(listOf("这是第一句。"), update.commits.map { it.text })
        assertEquals("这是第二句", update.active)
        assertFalse(update.commits.first().forced)
    }

    @Test
    fun `sentence boundary keeps closing punctuation`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val english = segmenter.update("He said \"Hello.\" Next")
        segmenter.reset()
        val chinese = segmenter.update("他说“你好。”然后继续")

        assertEquals(listOf("He said \"Hello.\""), english.commits.map { it.text })
        assertEquals("Next", english.active)
        assertEquals(listOf("他说“你好。”"), chinese.commits.map { it.text })
        assertEquals("然后继续", chinese.active)
    }

    @Test
    fun `unicode ellipsis is a sentence boundary`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.Sentence,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("Wait… Next")

        assertEquals(listOf("Wait…"), update.commits.map { it.text })
        assertEquals("Next", update.active)
    }

    @Test
    fun `all punctuation confirms a weak boundary before committing`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.All,
            nowMillis = { 1_000L },
        )

        val first = segmenter.update("Alpha, beta")
        val stable = segmenter.update("Alpha, beta continues")

        assertTrue(first.commits.isEmpty())
        assertEquals(listOf("Alpha,"), stable.commits.map { it.text })
        assertEquals("beta continues", stable.active)
    }

    @Test
    fun `all punctuation does not split numeric separators`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.All,
            nowMillis = { 1_000L },
        )

        segmenter.update("Value 1,234 remains")
        val update = segmenter.update("Value 1,234 remains stable")

        assertTrue(update.commits.isEmpty())
    }

    @Test
    fun `each identical weak boundary requires its own confirmation`() {
        val segmenter = RecognitionSegmenter(
            punctuationMode = PunctuationMode.All,
            nowMillis = { 1_000L },
        )
        segmenter.update("word, word")

        val update = segmenter.update("word, word, tail")

        assertEquals(listOf("word,"), update.commits.map { it.text })
        assertEquals("word, tail", update.active)
    }

    @Test
    fun `one large update splits until the tail is below the hard limit`() {
        val segmenter = RecognitionSegmenter(
            maxChars = 20,
            splitLookbackChars = 4,
            splitLookaheadChars = 5,
            nowMillis = { 1_000L },
        )

        val update = segmenter.update("x".repeat(80))

        assertEquals(listOf(25, 25, 25), update.commits.map { it.text.length })
        assertEquals("x".repeat(5), update.active)
    }

    @Test
    fun `empty update resets the consumed position and timer`() {
        var now = 1_000L
        val segmenter = RecognitionSegmenter(
            maxChars = 500,
            maxDurationMillis = 10_000L,
            nowMillis = { now },
        )
        segmenter.update("old partial")
        segmenter.update("")
        now = 20_000L

        val update = segmenter.update("new partial")

        assertTrue(update.commits.isEmpty())
        assertEquals("new partial", update.active)
    }
}
