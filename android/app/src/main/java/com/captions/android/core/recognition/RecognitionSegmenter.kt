package com.captions.android.core.recognition

data class SegmentCommit(
    val text: String,
    val forced: Boolean = false,
)

data class SegmentUpdate(
    val active: String,
    val commits: List<SegmentCommit> = emptyList(),
)

enum class PunctuationMode {
    Off,
    Sentence,
    All,
}

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
    var punctuationMode: PunctuationMode = PunctuationMode.Off,
    var minCommitChars: Int = 4,
    private val nowMillis: () -> Long = { System.nanoTime() / 1_000_000L },
) {
    private var raw = ""
    private var consumed = 0
    private var startedAt = 0L
    private var pendingWeakBoundary = ""

    val active: String
        get() = raw.substring(activeStart())

    fun reset() {
        raw = ""
        consumed = 0
        startedAt = 0L
        pendingWeakBoundary = ""
    }

    fun update(value: String): SegmentUpdate {
        val now = nowMillis()
        val normalized = value.trim().split(WHITESPACE).filter(String::isNotEmpty).joinToString(" ")
        if (normalized.isEmpty()) {
            reset()
            return SegmentUpdate("")
        }
        if (startedAt == 0L) startedAt = now
        if (consumed > 0 && !normalized.startsWith(raw.take(consumed))) {
            val reconciled = reconcileConsumed(raw.take(consumed), normalized)
            pendingWeakBoundary = ""
            if (reconciled == null) {
                reset()
                startedAt = now
            } else {
                consumed = reconciled
            }
        }
        raw = normalized
        val commits = mutableListOf<SegmentCommit>()

        if (punctuationMode != PunctuationMode.Off) {
            while (true) {
                val current = active
                val boundary = nextBoundary(current) ?: break
                val committed = current.substring(0, boundary).trim()
                consumed = activeStart() + boundary
                startedAt = now
                pendingWeakBoundary = ""
                commits += SegmentCommit(committed)
            }
        }

        var current = active
        if (current.isEmpty()) return SegmentUpdate("", commits)

        if (maxDurationMillis > 0 && now - startedAt >= maxDurationMillis) {
            val committed = current.trim()
            consumed = activeStart() + current.length
            startedAt = now
            commits += SegmentCommit(committed, forced = true)
            return SegmentUpdate(active, commits)
        }

        while (current.length > maxChars) {
            val decision = windowSplit(current) ?: break
            val committed = current.substring(0, decision.index).trim()
            consumed = activeStart() + decision.index
            startedAt = now
            commits += SegmentCommit(committed, decision.forced)
            current = active
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
            val end = terminalBoundaryEnd(text, match) ?: continue
            if (text.substring(0, end).trim().length < floor) continue
            pendingWeakBoundary = ""
            return end
        }

        if (punctuationMode == PunctuationMode.All) {
            for (match in WEAK_PUNCTUATION.findAll(text)) {
                val matchEnd = match.range.last + 1
                val end = withClosingPunctuation(text, matchEnd)
                if (text.substring(0, end).trim().length < floor) continue
                if (isNumericSeparator(text, match.range.first, matchEnd)) continue
                val candidate = text.substring(0, end).trim()
                val stable = candidate == pendingWeakBoundary
                pendingWeakBoundary = candidate
                if (stable) return end
                return null
            }
        }
        pendingWeakBoundary = ""
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

    private fun withClosingPunctuation(text: String, initialEnd: Int): Int {
        var end = initialEnd
        while (end < text.length && text[end] in CLOSING_PUNCTUATION) end += 1
        return end
    }

    private fun terminalBoundaryEnd(text: String, match: MatchResult): Int? {
        val end = withClosingPunctuation(text, match.range.last + 1)
        if (text[match.range.first] in ASCII_TERMINAL && end < text.length) {
            if (!text[end].isWhitespace()) return null
        }
        return end
    }

    private fun isNumericSeparator(text: String, start: Int, end: Int): Boolean =
        start > 0 && end < text.length && text[start - 1].isDigit() && text[end].isDigit()

    private fun windowSplit(text: String): SplitDecision? {
        val soft = maxOf(1, maxChars)
        val lookback = maxOf(0, splitLookbackChars)
        val lookahead = maxOf(0, splitLookaheadChars)
        val hard = soft + lookahead
        val start = maxOf(0, soft - lookback)
        val end = minOf(text.length, hard)
        val punctuation = mutableListOf<Pair<Int, Int>>()
        if (punctuationMode != PunctuationMode.Off) {
            for (match in TERMINAL_PUNCTUATION.findAll(text, start)) {
                if (match.range.first >= end) break
                if (isAbbreviation(text, match.range.first)) continue
                val boundary = terminalBoundaryEnd(text, match)
                if (boundary != null) punctuation += match.range.first to boundary
            }
            if (punctuationMode == PunctuationMode.All) {
                for (match in WEAK_PUNCTUATION.findAll(text, start)) {
                    if (match.range.first >= end) break
                    val matchEnd = match.range.last + 1
                    if (isNumericSeparator(text, match.range.first, matchEnd)) continue
                    punctuation += match.range.first to withClosingPunctuation(text, matchEnd)
                }
            }
            punctuation.sortBy { it.first }
        }
        if (punctuation.isNotEmpty()) {
            val selected = punctuation.firstOrNull { it.second >= soft } ?: punctuation.last()
            return SplitDecision(selected.second, forced = false)
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
        val distance = distances[bestIndex]
        return bestIndex.takeIf {
            it > 0 && distance < maxOf(previous.length, it) && distance <= allowedChanges
        }
    }

    private data class SplitDecision(val index: Int, val forced: Boolean)

    private companion object {
        val WHITESPACE = Regex("\\s+")
        val TERMINAL_PUNCTUATION = Regex("[。？！…]|[.?!]+")
        val WEAK_PUNCTUATION = Regex("[,，、;；:：]")
        val CLOSING_PUNCTUATION = setOf(
            '\"', '\'', '”', '’', '»', '」', '』', '】', '》', '）', '〕', '〗', '〙', '〛',
            ')', ']', '}',
        )
        val ASCII_TERMINAL = setOf('.', '?', '!')
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
