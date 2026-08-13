package com.captions.android.ports

import com.captions.android.core.session.TranslationSettings
import kotlinx.coroutines.flow.StateFlow

data class TranslationInput(
    val text: String,
    val context: List<String> = emptyList(),
)

fun interface TextTranslator {
    fun translate(input: TranslationInput, settings: TranslationSettings): String
}

interface TranslationSession : AutoCloseable {
    fun preview(
        cueId: Long,
        text: String,
        context: List<String>,
        settings: TranslationSettings,
        onResult: (Long, String) -> Unit,
    ): Boolean

    fun commit(
        cueId: Long,
        text: String,
        context: List<String>,
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

data class HttpRequest(
    val method: String,
    val url: String,
    val headers: Map<String, String> = emptyMap(),
    val body: String? = null,
    val timeoutMillis: Int = 15_000,
)

data class HttpResponse(
    val statusCode: Int,
    val body: String,
)

fun interface HttpClient {
    fun execute(request: HttpRequest): HttpResponse
}
