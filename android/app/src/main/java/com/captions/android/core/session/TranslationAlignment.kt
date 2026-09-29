package com.captions.android.core.session

private val whitespace = Regex("\\s+")
private const val trailingMarks = " .?!。？！…,，;；:：\"'”’»」』】）》)]}"

fun sourceExtendsTranslation(translatedSource: String, currentSource: String): Boolean {
    fun normalize(source: String) = source.trim().replace(whitespace, " ")
        .trimEnd { it in trailingMarks }.lowercase()
    val previous = normalize(translatedSource)
    return previous.isNotEmpty() && normalize(currentSource).startsWith(previous)
}
