package com.captions.android.platform.recognition

import org.junit.Assert.assertEquals
import org.junit.Test

class SystemRecognitionAccumulatorTest {
    @Test
    fun `system local partials become one cumulative stream`() {
        val accumulator = SystemRecognitionAccumulator()

        assertEquals("the goal is", accumulator.updatePartial("the goal is"))
        assertEquals("the goal is", accumulator.commit())
        assertEquals(
            "the goal is still growing",
            accumulator.updatePartial("still growing"),
        )
        assertEquals("the goal is still growing", accumulator.commit())
    }

    @Test
    fun `identical spoken segments remain distinct`() {
        val accumulator = SystemRecognitionAccumulator()

        accumulator.commit("one segment")
        accumulator.commit("one segment")

        assertEquals("one segment one segment", accumulator.text)
    }

    @Test
    fun `reset starts a fresh cumulative stream`() {
        val accumulator = SystemRecognitionAccumulator()
        accumulator.commit("old segment")

        accumulator.reset()

        assertEquals("new segment", accumulator.updatePartial("new segment"))
    }
}
