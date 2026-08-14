package com.captions.android.hymt

/**
 * In-process HyMT2 (llama.cpp STQ1_0) inference. Loads a GGUF model directly
 * in this process and generates translations synchronously.
 *
 * The native context is single-session and not thread-safe, so every entry
 * point is serialized on [engineLock]. Generation holds the lock for its whole
 * duration; load/unload therefore wait for any in-flight generation to finish
 * before touching the model, and two concurrent calls (preview + final) never
 * decode at the same time.
 */
object HyMt2Engine {
    init {
        System.loadLibrary("hy_mt2")
    }

    private val engineLock = Any()

    @Volatile
    var loaded: Boolean = false
        private set

    /** Loads the GGUF model into memory. Returns false on failure. */
    fun load(modelPath: String, nCtx: Int, nThreads: Int): Boolean = synchronized(engineLock) {
        val ok = nativeLoad(modelPath, nCtx, nThreads)
        loaded = ok
        ok
    }

    /** Generates a translation for [prompt], returning the model's text output. */
    fun generate(prompt: String, maxTokens: Int): String = synchronized(engineLock) {
        nativeGenerate(prompt, maxTokens)
    }

    /** Frees the loaded model and context. */
    fun unload() = synchronized(engineLock) {
        nativeUnload()
        loaded = false
    }

    private external fun nativeLoad(modelPath: String, nCtx: Int, nThreads: Int): Boolean
    private external fun nativeGenerate(prompt: String, maxTokens: Int): String
    private external fun nativeUnload()
}
