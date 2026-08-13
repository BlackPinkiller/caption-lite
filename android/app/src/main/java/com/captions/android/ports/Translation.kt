package com.captions.android.ports

import com.captions.android.core.session.TranslationSettings
import kotlinx.coroutines.flow.StateFlow

fun interface TextTranslator {
    fun translate(text: String, settings: TranslationSettings): String
}

interface TranslationSession : AutoCloseable {
    fun submit(
        cueId: Long,
        text: String,
        settings: TranslationSettings,
        onResult: (Long, String) -> Unit,
        onError: (String) -> Unit,
    ): Boolean

    fun cancelPending()
}

interface TranslationModelManager : AutoCloseable {
    val state: StateFlow<ModelState>

    fun configure(settings: TranslationSettings)
    fun download()
    fun isReady(settings: TranslationSettings): Boolean
}
