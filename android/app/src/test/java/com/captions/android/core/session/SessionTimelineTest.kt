package com.captions.android.core.session

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionTimelineTest {
    @Test
    fun partialUpdatesReplaceOnlyTheCurrentEntry() {
        val timeline = SessionTimeline()

        timeline.updateCurrent(1, "first partial")
        timeline.updateCurrent(1, "first complete")

        assertEquals(1, timeline.entries.size)
        assertEquals("first complete", timeline.entries.single().source)
        assertTrue(timeline.entries.single().current)
    }

    @Test
    fun committedEntriesRemainWhenTheNextCueStarts() {
        val timeline = SessionTimeline()
        timeline.updateCurrent(1, "first")
        timeline.commitCurrent()
        timeline.updateCurrent(2, "second")

        assertEquals(2, timeline.entries.size)
        assertFalse(timeline.entries[0].current)
        assertTrue(timeline.entries[1].current)
    }

    @Test
    fun translationUpdatesTheMatchingCue() {
        val timeline = SessionTimeline()
        timeline.updateCurrent(7, "source")

        assertTrue(timeline.updateTranslation(7, " translation "))
        assertEquals("translation", timeline.entries.single().translation)
        assertFalse(timeline.updateTranslation(99, "missing"))
    }
}
