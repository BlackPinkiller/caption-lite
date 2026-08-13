package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.HttpClient
import com.captions.android.ports.HttpRequest
import com.captions.android.ports.TextTranslator
import org.json.JSONArray

class Google2Translator(
    private val client: HttpClient,
) : TextTranslator {
    @Volatile
    private var apiKey: String = ""

    override fun translate(text: String, settings: TranslationSettings): String {
        val key = apiKey.ifEmpty { acquireApiKey(settings.timeoutMillis).also { apiKey = it } }
        val payload = JSONArray().apply {
            put(JSONArray().apply {
                put(JSONArray().put(text))
                put(googleCode(settings.sourceLanguage))
                put(googleCode(settings.targetLanguage))
            })
            put("wt_lib")
        }
        val response = client.execute(
            HttpRequest(
                method = "POST",
                url = TRANSLATE_URL,
                headers = mapOf(
                    "Content-Type" to "application/json+protobuf",
                    "X-Goog-API-Key" to key,
                ),
                body = payload.toString(),
                timeoutMillis = settings.timeoutMillis,
            ),
        )
        checkSuccess(response.statusCode, "Google 翻译")
        return runCatching {
            JSONArray(response.body).getJSONArray(0).getString(0).trim()
        }.getOrElse { error("Google 翻译返回异常") }
    }

    private fun acquireApiKey(timeoutMillis: Int): String {
        val bootstrap = client.execute(
            HttpRequest(
                method = "GET",
                url = BOOTSTRAP_URL,
                headers = mapOf("User-Agent" to USER_AGENT),
                timeoutMillis = timeoutMillis,
            ),
        )
        checkSuccess(bootstrap.statusCode, "Google 翻译")
        val mainUrl = LOAD_SCRIPT.findAll(bootstrap.body)
            .map { decodeScriptUrl(it.groupValues[1]) }
            .firstOrNull {
                it.startsWith("https://translate.googleapis.com/") &&
                    "translate_http" in it && it.endsWith("/m=el_main")
            }
            ?: error("Google 翻译暂时不可用")
        val script = client.execute(
            HttpRequest(
                method = "GET",
                url = mainUrl,
                headers = mapOf("User-Agent" to USER_AGENT),
                timeoutMillis = timeoutMillis,
            ),
        )
        checkSuccess(script.statusCode, "Google 翻译")
        return API_KEY.find(script.body)?.groupValues?.get(1)
            ?: error("Google 翻译暂时不可用")
    }

    private fun decodeScriptUrl(value: String): String = value
        .replace(HEX_ESCAPE) { it.groupValues[1].toInt(16).toChar().toString() }
        .replace(UNICODE_ESCAPE) { it.groupValues[1].toInt(16).toChar().toString() }
        .replace("\\/", "/")

    private fun googleCode(code: String): String = when (code) {
        "zh" -> "zh-CN"
        else -> code
    }

    private fun checkSuccess(statusCode: Int, service: String) {
        if (statusCode !in 200..299) error("${service}请求失败（$statusCode）")
    }

    private companion object {
        const val BOOTSTRAP_URL =
            "https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"
        const val TRANSLATE_URL = "https://translate-pa.googleapis.com/v1/translateHtml"
        const val USER_AGENT = "Mozilla/5.0"
        val LOAD_SCRIPT = Regex("_loadJs\\('([^']+)'\\)")
        val API_KEY = Regex(
            "/v1/translateHtml.{0,500}?X-goog-api-key\\\"?:\\\"(AIza[0-9A-Za-z_-]{35})\\\"",
            setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
        )
        val HEX_ESCAPE = Regex("\\\\x([0-9a-fA-F]{2})")
        val UNICODE_ESCAPE = Regex("\\\\u([0-9a-fA-F]{4})")
    }
}
