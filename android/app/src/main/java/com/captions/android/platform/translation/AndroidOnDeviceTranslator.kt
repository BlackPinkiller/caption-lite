package com.captions.android.platform.translation

import android.content.Context
import android.icu.util.ULocale
import android.os.CancellationSignal
import android.view.translation.TranslationContext
import android.view.translation.TranslationManager
import android.view.translation.TranslationRequest
import android.view.translation.TranslationRequestValue
import android.view.translation.TranslationResponse
import android.view.translation.TranslationResponseValue
import android.view.translation.TranslationSpec
import android.view.translation.Translator
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput
import com.captions.android.ports.TranslationModelManager
import java.util.concurrent.CompletableFuture
import java.util.concurrent.Executor
import java.util.concurrent.TimeUnit

class AndroidOnDeviceTranslator(
    context: Context,
    private val modelManager: TranslationModelManager,
) : TextTranslator {
    private val manager = checkNotNull(context.getSystemService(TranslationManager::class.java)) {
        "系统本地翻译不可用"
    }
    private val clients = mutableMapOf<LanguagePair, Translator>()
    private val clientLock = Any()
    private var closed = false

    override fun translate(input: TranslationInput, settings: TranslationSettings): String {
        if (sameLanguage(settings.sourceLanguage, settings.targetLanguage)) return input.text
        check(modelManager.isReady(settings)) { "请先下载系统翻译模型" }
        val translator = client(settings)
        val request = TranslationRequest.Builder()
            .setTranslationRequestValues(listOf(TranslationRequestValue.forText(input.text)))
            .build()
        val result = CompletableFuture<String>()
        val cancellation = CancellationSignal()
        translator.translate(request, cancellation, DIRECT_EXECUTOR) { response ->
            val translated = response.translationResponseValues[0]
            if (
                response.translationStatus == TranslationResponse.TRANSLATION_STATUS_SUCCESS &&
                translated?.statusCode == TranslationResponseValue.STATUS_SUCCESS &&
                !translated.text.isNullOrBlank()
            ) {
                result.complete(translated.text.toString())
            } else {
                result.completeExceptionally(IllegalStateException("系统本地翻译失败"))
            }
        }
        return try {
            result.get(TRANSLATION_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        } finally {
            if (!result.isDone) cancellation.cancel()
        }
    }

    private fun client(settings: TranslationSettings): Translator = synchronized(clientLock) {
        check(!closed) { "系统本地翻译已关闭" }
        val pair = LanguagePair(settings.sourceLanguage, settings.targetLanguage)
        clients[pair]?.takeUnless(Translator::isDestroyed)?.let { return it }
        val source = TranslationSpec(
            ULocale.forLanguageTag(settings.sourceLanguage),
            TranslationSpec.DATA_FORMAT_TEXT,
        )
        val target = TranslationSpec(
            ULocale.forLanguageTag(settings.targetLanguage),
            TranslationSpec.DATA_FORMAT_TEXT,
        )
        val context = TranslationContext.Builder(source, target).build()
        val created = CompletableFuture<Translator>()
        manager.createOnDeviceTranslator(context, DIRECT_EXECUTOR) { translator ->
            if (translator == null) {
                created.completeExceptionally(IllegalStateException("无法启动系统本地翻译"))
            } else {
                created.complete(translator)
            }
        }
        created.get(CREATE_TIMEOUT_SECONDS, TimeUnit.SECONDS).also { clients[pair] = it }
    }

    override fun close() {
        val currentClients = synchronized(clientLock) {
            if (closed) return
            closed = true
            clients.values.toList().also { clients.clear() }
        }
        currentClients.forEach(Translator::destroy)
    }

    private data class LanguagePair(val source: String, val target: String)

    private companion object {
        val DIRECT_EXECUTOR = Executor(Runnable::run)
        const val CREATE_TIMEOUT_SECONDS = 15L
        const val TRANSLATION_TIMEOUT_SECONDS = 30L
    }
}
