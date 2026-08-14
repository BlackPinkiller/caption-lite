package com.captions.android.core.session

class SessionTimeline {
    private val mutableEntries = mutableListOf<SessionEntry>()

    val entries: List<SessionEntry>
        get() = mutableEntries.toList()

    fun updateCurrent(cueId: Long, source: String, translation: String? = null) {
        val last = mutableEntries.lastOrNull()
        val next = SessionEntry(
            cueId = cueId,
            source = source.trim(),
            translation = translation?.trim()
                ?: last?.takeIf { it.current && it.cueId == cueId }?.translation.orEmpty(),
            current = true,
        )
        if (last?.current == true && last.cueId == cueId) {
            mutableEntries[mutableEntries.lastIndex] = next
        } else {
            if (last?.current == true) {
                mutableEntries[mutableEntries.lastIndex] = last.copy(current = false)
            }
            mutableEntries += next
        }
    }

    fun commitCurrent() {
        // The latest sentence keeps its highlight until the next one begins;
        // committing only finalizes its text, it does not re-style it as history.
    }

    fun updateTranslation(cueId: Long, translation: String): Boolean {
        val index = mutableEntries.indexOfLast { it.cueId == cueId }
        if (index < 0) return false
        mutableEntries[index] = mutableEntries[index].copy(translation = translation.trim())
        return true
    }

    fun clear() {
        mutableEntries.clear()
    }
}
