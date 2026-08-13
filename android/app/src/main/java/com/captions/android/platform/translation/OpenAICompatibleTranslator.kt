package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.translation.renderPrompt
import com.captions.android.ports.HttpClient
import com.captions.android.ports.HttpRequest
import com.captions.android.ports.TextTranslator
import com.captions.android.ports.TranslationInput
import org.json.JSONArray
import org.json.JSONObject

class OpenAICompatibleTranslator(
    private val client: HttpClient,
) : TextTranslator {
    override fun translate(input: TranslationInput, settings: TranslationSettings): String {
        val url = chatCompletionsUrl(settings.llmBaseUrl)
        require(url.isNotEmpty()) { "请填写 LLM API 地址" }
        val context = input.context.joinToString("\n").let {
            if (it.isEmpty()) "" else "仅供消歧的上文（不要翻译）：\n$it"
        }
        val prompt = renderPrompt(
            settings.llmPromptTemplate,
            mapOf(
                "src" to languageName(settings.sourceLanguage),
                "dst" to languageName(settings.targetLanguage),
                "ctx" to context,
                "terms" to "",
                "text" to input.text,
            ),
        )
        val payload = JSONObject().apply {
            put(
                "messages",
                JSONArray().put(
                    JSONObject()
                        .put("role", "user")
                        .put("content", prompt),
                ),
            )
            put("temperature", 0.1)
            put("stream", false)
            put("max_tokens", 1_024)
            if (settings.llmModel.isNotBlank()) put("model", settings.llmModel.trim())
        }
        val headers = mutableMapOf("Content-Type" to "application/json")
        if (settings.llmApiKey.isNotBlank()) {
            headers["Authorization"] = "Bearer ${settings.llmApiKey.trim()}"
        }
        val response = client.execute(
            HttpRequest(
                method = "POST",
                url = url,
                headers = headers,
                body = payload.toString(),
                timeoutMillis = settings.timeoutMillis,
            ),
        )
        if (response.statusCode !in 200..299) {
            error("LLM 请求失败（${response.statusCode}）")
        }
        return runCatching {
            JSONObject(response.body)
                .getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .getString("content")
                .trim()
        }.getOrElse { error("LLM 返回异常") }
    }

    private fun chatCompletionsUrl(baseUrl: String): String {
        val normalized = baseUrl.trim().trimEnd('/')
        return when {
            normalized.isEmpty() -> ""
            normalized.endsWith("/chat/completions", ignoreCase = true) -> normalized
            else -> "$normalized/chat/completions"
        }
    }

    private fun languageName(code: String): String = when (code) {
        "en" -> "英语"
        "zh" -> "中文"
        "ja" -> "日语"
        "ko" -> "韩语"
        "de" -> "德语"
        "fr" -> "法语"
        "es" -> "西班牙语"
        "it" -> "意大利语"
        "pt" -> "葡萄牙语"
        "ru" -> "俄语"
        else -> code
    }
}
