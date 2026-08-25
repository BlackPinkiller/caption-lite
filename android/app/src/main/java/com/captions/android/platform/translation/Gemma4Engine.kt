package com.captions.android.platform.translation

import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.ThinkingConfig
import java.util.concurrent.TimeUnit

/**
 * In-process Gemma 4 E2B inference backed by LiteRT-LM. Loads a `.litertlm`
 * model and generates translations synchronously.
 *
 * LiteRT-LM conversations accumulate history, so every generation uses a
 * fresh conversation (each prompt already embeds its own background context).
 * All entry points are serialized on [lock] because the native engine is not
 * thread-safe and the model must stay loaded while a call is in flight.
 */
class Gemma4Engine(private val cacheDir: String) : AutoCloseable {
    private val lock = Any()
    private var engine: Engine? = null

    val loaded: Boolean
        get() = synchronized(lock) { engine?.isInitialized() == true }

    fun load(modelPath: String, backend: Backend): Boolean = synchronized(lock) {
        closeLocked()
        return runCatching {
            @OptIn(ExperimentalApi::class)
            ExperimentalFlags.enableBenchmark = true
            Engine(
                EngineConfig(
                    modelPath = modelPath,
                    backend = backend,
                    cacheDir = cacheDir,
                ),
            ).also { it.initialize() }
        }.onSuccess {
            engine = it
            Log.i(LOG_TAG, "engine initialized, backend = ${backend.name}")
        }.onFailure {
            Log.e(LOG_TAG, "engine init failed", it)
        }.isSuccess
    }

    fun generate(prompt: String, maxTokens: Int): String = synchronized(lock) {
        val current = engine ?: return ""
        return try {
            current.createConversation(
                ConversationConfig(
                    systemInstruction = Contents.of(SYSTEM_INSTRUCTION),
                    samplerConfig = SamplerConfig(topK = 64, topP = 0.95, temperature = 1.0),
                    thinkingConfig = ThinkingConfig(enableThinking = false),
                    extraContext = mapOf("enable_thinking" to false),
                    maxOutputToken = maxTokens,
                ),
            ).use { conversation ->
                val started = System.nanoTime()
                val response = conversation.sendMessage(prompt)
                val wallMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started)
                val text = response.toString().trim()
                logBenchmark(conversation, wallMs, text)
                text
            }
        } catch (error: Throwable) {
            Log.e(LOG_TAG, "generate failed", error)
            ""
        }
    }

    override fun close() = synchronized(lock) {
        closeLocked()
    }

    private fun closeLocked() {
        val current = engine
        engine = null
        if (current != null) {
            runCatching { current.close() }
        }
    }

    @OptIn(ExperimentalApi::class)
    private fun logBenchmark(conversation: Conversation, wallMs: Long, text: String) {
        runCatching {
            val info = conversation.getBenchmarkInfo()
            Log.i(
                LOG_TAG,
                (
                    "benchmark wall_ms=%d ttft_s=%.3f prefill_tokens=%d prefill_tok_s=%.1f " +
                        "decode_tokens=%d decode_tok_s=%.1f out_len=%d first_char=%.40s"
                ).format(
                    wallMs,
                    info.timeToFirstTokenInSecond,
                    info.lastPrefillTokenCount,
                    info.lastPrefillTokensPerSecond,
                    info.lastDecodeTokenCount,
                    info.lastDecodeTokensPerSecond,
                    text.length,
                    text,
                ),
            )
        }
    }

    private companion object {
        const val LOG_TAG = "Gemma4"
        const val SYSTEM_INSTRUCTION =
            "You are a translation engine. Translate the user's text into the requested target " +
                "language. Output ONLY the translated text, without explanations, alternatives, " +
                "notes, or any extra content."
    }
}
