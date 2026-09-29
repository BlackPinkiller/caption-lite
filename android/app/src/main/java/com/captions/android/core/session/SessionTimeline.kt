package com.captions.android.core.session

class SessionTimeline(
    maxEntries: Int = DEFAULT_MAX_ENTRIES,
) {
    private val mutableEntries = mutableListOf<SessionEntry>()
    private val historyLimit = maxEntries.coerceAtLeast(1)
    private var currentTranslationSource = ""

    val entries: List<SessionEntry>
        get() = mutableEntries.toList()

    fun updateCurrent(cueId: Long, source: String, translation: String? = null) {
        val current = mutableEntries.lastOrNull()
        val keepTranslation = current?.current == true && current.cueId == cueId &&
            sourceExtendsTranslation(currentTranslationSource, source)
        currentTranslationSource = when {
            translation != null -> source.trim()
            keepTranslation -> currentTranslationSource
            else -> ""
        }
        val next = SessionEntry(
            cueId = cueId,
            source = source.trim(),
            translation = translation?.trim()
                ?: current?.takeIf { keepTranslation }?.translation.orEmpty(),
            current = true,
        )
        if (current?.current == true) {
            mutableEntries[mutableEntries.lastIndex] = next
        } else {
            mutableEntries += next
            if (mutableEntries.size > historyLimit) {
                mutableEntries.removeAt(0)
            }
        }
    }

    fun commitCurrent() {
        val current = mutableEntries.lastOrNull() ?: return
        if (current.current) {
            mutableEntries[mutableEntries.lastIndex] = current.copy(current = false)
            currentTranslationSource = ""
        }
    }

    fun updateTranslation(cueId: Long, translation: String, source: String? = null): Boolean {
        val index = mutableEntries.indexOfLast { it.cueId == cueId }
        if (index < 0) return false
        val entry = mutableEntries[index]
        val translatedSource = source ?: entry.source
        if (!sourceExtendsTranslation(translatedSource, entry.source)) return false
        if (entry.current) currentTranslationSource = translatedSource
        mutableEntries[index] = mutableEntries[index].copy(translation = translation.trim())
        return true
    }

    fun clear() {
        mutableEntries.clear()
        currentTranslationSource = ""
    }

    private companion object {
        const val DEFAULT_MAX_ENTRIES = 5_000
    }
}
