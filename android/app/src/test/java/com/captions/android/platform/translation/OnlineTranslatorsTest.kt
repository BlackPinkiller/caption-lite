package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.HttpClient
import com.captions.android.ports.HttpRequest
import com.captions.android.ports.HttpResponse
import com.captions.android.ports.TranslationInput
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OnlineTranslatorsTest {
    @Test
    fun google2BootstrapsItsKeyAndSendsTheExpectedLanguagePair() {
        val key = "AIza" + "a".repeat(35)
        val client = RecordingHttpClient(
            HttpResponse(
                200,
                "_loadJs('https://translate.googleapis.com/_/translate_http/_/js/k=translate_http/m=el_main')",
            ),
            HttpResponse(200, "/v1/translateHtml abc X-goog-api-key\":\"$key\""),
            HttpResponse(200, "[[\"你好\"]]"),
        )

        val result = Google2Translator(client).translate(
            TranslationInput("hello"),
            TranslationSettings(),
        )

        assertEquals("你好", result)
        val request = client.requests.last()
        assertEquals("POST", request.method)
        assertEquals(key, request.headers["X-Goog-API-Key"])
        val payload = JSONArray(request.body!!)
        assertEquals("en", payload.getJSONArray(0).getString(1))
        assertEquals("zh-CN", payload.getJSONArray(0).getString(2))
    }

    @Test
    fun google2RefreshesARejectedCachedKeyOnce() {
        val oldKey = "AIza" + "a".repeat(35)
        val newKey = "AIza" + "b".repeat(35)
        val bootstrap =
            "_loadJs('https://translate.googleapis.com/_/translate_http/_/js/k=translate_http/m=el_main')"
        val client = RecordingHttpClient(
            HttpResponse(200, bootstrap),
            HttpResponse(200, "/v1/translateHtml X-goog-api-key\":\"" + oldKey + "\""),
            HttpResponse(200, "[[\"首次\"]]"),
            HttpResponse(403, ""),
            HttpResponse(200, bootstrap),
            HttpResponse(200, "/v1/translateHtml X-goog-api-key\":\"" + newKey + "\""),
            HttpResponse(200, "[[\"刷新后\"]]"),
        )
        val translator = Google2Translator(client)
        val settings = TranslationSettings()

        assertEquals("首次", translator.translate(TranslationInput("first"), settings))
        assertEquals("刷新后", translator.translate(TranslationInput("second"), settings))

        val translationRequests = client.requests.filter { it.method == "POST" }
        assertEquals(listOf(oldKey, oldKey, newKey), translationRequests.map {
            it.headers["X-Goog-API-Key"]
        })
    }

    @Test
    fun deepLUsesTheSelectedPlanAndKeepsTheKeyOutOfTheBody() {
        val client = RecordingHttpClient(
            HttpResponse(200, "{\"translations\":[{\"text\":\"你好\"}]}")
        )

        val result = DeepLTranslator(client).translate(
            TranslationInput("hello"),
            TranslationSettings(deeplApiKey = "secret", deeplPro = true),
        )

        assertEquals("你好", result)
        val request = client.requests.single()
        assertEquals("https://api.deepl.com/v2/translate", request.url)
        assertEquals("DeepL-Auth-Key secret", request.headers["Authorization"])
        assertTrue("secret" !in request.body.orEmpty())
        val body = JSONObject(request.body!!)
        assertEquals("EN", body.getString("source_lang"))
        assertEquals("ZH-HANS", body.getString("target_lang"))
    }

    @Test
    fun openAICompatibleUsesContextAndTheChatCompletionsContract() {
        val client = RecordingHttpClient(
            HttpResponse(200, "{\"choices\":[{\"message\":{\"content\":\"你好\"}}]}")
        )

        val result = OpenAICompatibleTranslator(client).translate(
            TranslationInput("current", listOf("earlier sentence")),
            TranslationSettings(
                llmBaseUrl = "http://localhost:8080/v1/",
                llmModel = "local-model",
                llmApiKey = "secret",
            ),
        )

        assertEquals("你好", result)
        val request = client.requests.single()
        assertEquals("http://localhost:8080/v1/chat/completions", request.url)
        assertEquals("Bearer secret", request.headers["Authorization"])
        val body = JSONObject(request.body!!)
        assertEquals(false, body.getBoolean("stream"))
        assertEquals("local-model", body.getString("model"))
        val prompt = body.getJSONArray("messages").getJSONObject(0).getString("content")
        assertTrue("earlier sentence" in prompt)
        assertTrue("current" in prompt)
        assertTrue("secret" !in request.body.orEmpty())
    }

    private class RecordingHttpClient(
        vararg responses: HttpResponse,
    ) : HttpClient {
        private val responses = ArrayDeque(responses.toList())
        val requests = mutableListOf<HttpRequest>()

        override fun execute(request: HttpRequest): HttpResponse {
            requests += request
            return responses.removeFirst()
        }
    }
}
