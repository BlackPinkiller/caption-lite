package com.captions.android.core.session

class SessionTimeline {
    private val mutableEntries = mutableListOf<SessionEntry>()

    val entries: List<SessionEntry>
        get() = mutableEntries.toList()

    fun updateCurrent(cueId: Long, source: String, translation: String = "") {
        val next = SessionEntry(
            cueId = cueId,
            source = source.trim(),
            translation = translation.trim(),
            current = true,
        )
        if (mutableEntries.lastOrNull()?.current == true) {
            mutableEntries[mutableEntries.lastIndex] = next
        } else {
            mutableEntries += next
        }
    }

    fun commitCurrent() {
        val current = mutableEntries.lastOrNull() ?: return
        if (current.current) {
            mutableEntries[mutableEntries.lastIndex] = current.copy(current = false)
        }
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
