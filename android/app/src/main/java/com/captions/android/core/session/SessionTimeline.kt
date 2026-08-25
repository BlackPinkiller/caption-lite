package com.captions.android.core.session

class SessionTimeline(
    maxEntries: Int = DEFAULT_MAX_ENTRIES,
) {
    private val mutableEntries = mutableListOf<SessionEntry>()
    private val historyLimit = maxEntries.coerceAtLeast(1)

    val entries: List<SessionEntry>
        get() = mutableEntries.toList()

    fun updateCurrent(cueId: Long, source: String, translation: String? = null) {
        val current = mutableEntries.lastOrNull()
        val next = SessionEntry(
            cueId = cueId,
            source = source.trim(),
            translation = translation?.trim()
                ?: current?.takeIf { it.current && it.cueId == cueId }?.translation.orEmpty(),
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

    private companion object {
        const val DEFAULT_MAX_ENTRIES = 5_000
    }
}
