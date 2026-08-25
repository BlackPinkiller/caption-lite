package com.captions.android.core.translation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class PromptTemplateTest {
    @Test
    fun rendersOnlySupportedPlaceholders() {
        val rendered = renderPrompt(
            "{src}>{dst}\n{ctx}\n{text}\n{unknown}",
            mapOf("src" to "EN", "dst" to "ZH", "ctx" to "before", "text" to "now"),
        )

        assertEquals("EN>ZH\nbefore\nnow\n{unknown}", rendered)
    }

    @Test
    fun requiresTheCurrentTextPlaceholder() {
        assertThrows(IllegalArgumentException::class.java) {
            renderPrompt("translate this", emptyMap())
        }
    }
}
