package com.captions.android.platform.recognition

internal class SystemRecognitionAccumulator {
    private val completed = mutableListOf<String>()
    private var partial = ""

    val text: String
        get() = (completed + listOfNotNull(partial.takeIf(String::isNotEmpty))).joinToString(" ")

    fun updatePartial(value: String): String {
        partial = value.normalized()
        return text
    }

    fun commit(value: String? = null): String? {
        val segment = value?.normalized().orEmpty().ifEmpty { partial }
        partial = ""
        if (segment.isEmpty()) return null
        completed += segment
        return text
    }

    fun reset() {
        completed.clear()
        partial = ""
    }

    private fun String.normalized(): String = trim().split(WHITESPACE)
        .filter(String::isNotEmpty)
        .joinToString(" ")

    private companion object {
        val WHITESPACE = Regex("\\s+")
    }
}
