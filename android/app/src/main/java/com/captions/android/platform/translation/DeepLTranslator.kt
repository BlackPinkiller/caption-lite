package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.HttpClient
import com.captions.android.ports.HttpRequest
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput
import org.json.JSONArray
import org.json.JSONObject

class DeepLTranslator(
    private val client: HttpClient,
) : TextTranslator {
    override fun translate(input: TranslationInput, settings: TranslationSettings): String {
        val apiKey = settings.deeplApiKey.trim()
        require(apiKey.isNotEmpty()) { "请填写 DeepL API 密钥" }
        val payload = JSONObject().apply {
            put("text", JSONArray().put(input.text))
            put("source_lang", deepLCode(settings.sourceLanguage))
            put("target_lang", deepLCode(settings.targetLanguage, target = true))
        }
        val host = if (settings.deeplPro) "api.deepl.com" else "api-free.deepl.com"
        val response = client.execute(
            HttpRequest(
                method = "POST",
                url = "https://$host/v2/translate",
                headers = mapOf(
                    "Authorization" to "DeepL-Auth-Key $apiKey",
                    "Content-Type" to "application/json",
                    "User-Agent" to "RealtimeSubtitle-Android/1.0",
                ),
                body = payload.toString(),
                timeoutMillis = settings.timeoutMillis,
            ),
        )
        if (response.statusCode !in 200..299) {
            error("DeepL 请求失败（${response.statusCode}）")
        }
        return runCatching {
            JSONObject(response.body)
                .getJSONArray("translations")
                .getJSONObject(0)
                .getString("text")
                .trim()
        }.getOrElse { error("DeepL 返回异常") }
    }

    private fun deepLCode(code: String, target: Boolean = false): String = when (code) {
        "zh" -> if (target) "ZH-HANS" else "ZH"
        else -> code.uppercase()
    }
}
