package com.captions.android.core.recognition

data class SegmentCommit(
    val text: String,
    val forced: Boolean = false,
)

data class SegmentUpdate(
    val active: String,
    val commits: List<SegmentCommit> = emptyList(),
)

object SegmentationRules {
    fun shouldCommitEndpoint(
        text: String,
        vadEndpoint: Boolean,
        asrEndpoint: Boolean,
        minChars: Int,
    ): Boolean {
        if (asrEndpoint) return true
        return vadEndpoint && text.trim().length >= maxOf(1, minChars)
    }
}

class RecognitionSegmenter(
    var maxChars: Int = 160,
    var maxDurationMillis: Long = 20_000L,
    var splitLookbackChars: Int = 32,
    var splitLookaheadChars: Int = 160,
    var splitPunctuation: Boolean = true,
    var minCommitChars: Int = 4,
    private val nowMillis: () -> Long = { System.nanoTime() / 1_000_000L },
) {
    private var raw = ""
    private var consumed = 0
    private var startedAt = 0L

    val active: String
        get() = raw.substring(activeStart())

    fun reset() {
        raw = ""
        consumed = 0
        startedAt = 0L
    }

    fun update(value: String): SegmentUpdate {
        val now = nowMillis()
        val normalized = value.trim().split(WHITESPACE).filter(String::isNotEmpty).joinToString(" ")
        if (normalized.isEmpty()) {
            raw = ""
            return SegmentUpdate("")
        }
        if (startedAt == 0L) startedAt = now
        if (consumed > 0 && !normalized.startsWith(raw.take(consumed))) {
            val reconciled = reconcileConsumed(raw.take(consumed), normalized)
            if (reconciled == null) {
                reset()
                startedAt = now
            } else {
                consumed = reconciled
            }
        }
        raw = normalized
        val commits = mutableListOf<SegmentCommit>()

        if (splitPunctuation) {
            while (true) {
                val current = active
                val boundary = nextBoundary(current)
                if (boundary == null) break
                val committed = current.substring(0, boundary).trim()
                consumed = activeStart() + boundary
                startedAt = now
                commits += SegmentCommit(committed)
            }
        }

        val current = active
        if (current.isEmpty()) return SegmentUpdate("", commits)

        if (maxDurationMillis > 0 && now - startedAt >= maxDurationMillis) {
            val committed = current.trim()
            consumed = activeStart() + current.length
            startedAt = now
            commits += SegmentCommit(committed, forced = true)
            return SegmentUpdate(active, commits)
        }

        if (current.length > maxChars) {
            val decision = windowSplit(current) ?: return SegmentUpdate(current, commits)
            val committed = current.substring(0, decision.index).trim()
            consumed = activeStart() + decision.index
            startedAt = now
            commits += SegmentCommit(committed, decision.forced)
        }
        return SegmentUpdate(active, commits)
    }

    fun flush(forced: Boolean = false): SegmentUpdate {
        val current = active
        reset()
        return if (current.isEmpty()) SegmentUpdate("")
        else SegmentUpdate("", listOf(SegmentCommit(current, forced)))
    }

    private fun activeStart(): Int {
        var start = consumed
        while (start < raw.length && raw[start].isWhitespace()) start += 1
        return start
    }

    private fun nextBoundary(text: String): Int? {
        val floor = maxOf(1, minCommitChars)
        for (match in TERMINAL_PUNCTUATION.findAll(text)) {
            if (isAbbreviation(text, match.range.first)) continue
            val end = match.range.last + 1
            if (text.substring(0, end).trim().length < floor) continue
            return end
        }
        return null
    }

    private fun isAbbreviation(text: String, pos: Int): Boolean {
        if (text[pos] != '.') return false
        val prefix = text.substring(0, pos)
        val match = Regex("[A-Za-z][\\w.]*\\s*$").find(prefix) ?: return false
        val token = match.value.trim()
        if (token.length == 1 && token[0].isUpperCase()) return true
        if (token.all { it.isUpperCase() || it == '.' } && token.contains('.')) return true
        return token.lowercase() in ABBREVIATIONS
    }

    private fun windowSplit(text: String): SplitDecision? {
        val soft = maxOf(1, maxChars)
        val lookback = maxOf(0, splitLookbackChars)
        val lookahead = maxOf(0, splitLookaheadChars)
        val hard = soft + lookahead
        val start = maxOf(0, soft - lookback)
        val end = minOf(text.length, hard)
        val window = text.substring(start, end)
        val punctuation = mutableListOf<MatchResult>()
        if (splitPunctuation) {
            punctuation += TERMINAL_PUNCTUATION.findAll(window)
                .filter { !isAbbreviation(text, start + it.range.first) }
                .toList()
        }
        if (punctuation.isNotEmpty()) {
            val selected = punctuation.firstOrNull { start + it.range.last + 1 >= soft }
                ?: punctuation.last()
            return SplitDecision(start + selected.range.last + 1, forced = false)
        }
        if (text.length < hard) return null
        val floor = maxOf(0, hard - lookback)
        val head = text.substring(0, minOf(hard, text.length))
        val position = head.lastIndexOf(' ', startIndex = head.lastIndex)
        val split = position.takeIf { it > floor } ?: minOf(hard, text.length)
        return SplitDecision(split, forced = true)
    }

    private fun reconcileConsumed(previousPrefix: String, revised: String): Int? {
        val previous = previousPrefix.trimEnd()
        if (previous.isEmpty()) return null
        var distances = IntArray(revised.length + 1) { it }
        previous.forEachIndexed { oldIndex, oldChar ->
            val next = IntArray(revised.length + 1)
            next[0] = oldIndex + 1
            revised.forEachIndexed { newIndex, newChar ->
                val substitution = distances[newIndex] + if (oldChar == newChar) 0 else 1
                val deletion = distances[newIndex + 1] + 1
                val insertion = next[newIndex] + 1
                next[newIndex + 1] = minOf(substitution, deletion, insertion)
            }
            distances = next
        }
        val bestIndex = distances.indices.minWithOrNull(
            compareBy<Int> { distances[it] }.thenBy { kotlin.math.abs(it - previous.length) },
        ) ?: return null
        val allowedChanges = maxOf(MIN_RECONCILE_CHANGES, previous.length / 3)
        return bestIndex.takeIf { distances[it] <= allowedChanges }
    }

    private data class SplitDecision(val index: Int, val forced: Boolean)

    private companion object {
        val WHITESPACE = Regex("\\s+")
        val TERMINAL_PUNCTUATION = Regex("[。？！]|[.?!](?=\\s|$)")
        const val MIN_RECONCILE_CHANGES = 4
        val ABBREVIATIONS = setOf(
            "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
            "e.g", "i.e", "inc", "ltd", "co", "corp", "dept", "no", "fig",
            "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct",
            "nov", "dec", "mon", "tue", "wed", "thu", "fri", "sat", "sun",
            "u.s", "u.k", "ave", "blvd", "rd", "sq", "mt", "hwy",
        )
    }
}
