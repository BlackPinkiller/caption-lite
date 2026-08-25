package com.captions.android.core.translation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HyMt2PromptTest {
    @Test
    fun englishSourceUsesEnglishPromptAndEnglishTargetName() {
        val prompt = HyMt2Prompt.build(
            sourceLanguage = "en",
            targetLanguage = "zh",
            text = "Hello",
            context = emptyList(),
        )
        assertTrue(prompt.startsWith("Translate the following text into Chinese"))
        assertTrue(prompt.endsWith("Hello"))
    }

    @Test
    fun chineseSourceUsesChinesePromptAndChineseTargetName() {
        val prompt = HyMt2Prompt.build(
            sourceLanguage = "zh",
            targetLanguage = "en",
            text = "你好",
            context = emptyList(),
        )
        assertTrue(prompt.startsWith("将以下文本翻译为 英语"))
        assertTrue(prompt.endsWith("你好"))
    }

    @Test
    fun backgroundContextUsesTheBackgroundInformationVariant() {
        val prompt = HyMt2Prompt.build(
            sourceLanguage = "en",
            targetLanguage = "ja",
            text = "Run it",
            context = listOf("a = 运行", "b = 测试"),
        )
        assertTrue(prompt.contains("[Background Information]"))
        assertTrue(prompt.contains("a = 运行"))
        assertTrue(prompt.contains("Japanese"))
    }

    @Test
    fun sameLanguageSourceNameFallsBackToTheCode() {
        val prompt = HyMt2Prompt.build(
            sourceLanguage = "en",
            targetLanguage = "xx",
            text = "Hello",
            context = emptyList(),
        )
        assertTrue(prompt.contains("into xx"))
    }

    @Test
    fun regionalSourceIsStillRecognisedAsChinese() {
        val prompt = HyMt2Prompt.build(
            sourceLanguage = "zh-Hans-CN",
            targetLanguage = "en",
            text = "你好",
            context = emptyList(),
        )
        assertTrue(prompt.startsWith("将以下文本翻译为 英语"))
    }
}
