package com.captions.android.platform.translation

import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.HttpClient
import com.captions.android.ports.HttpRequest
import com.captions.android.ports.HttpResponse
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

        val result = Google2Translator(client).translate("hello", TranslationSettings())

        assertEquals("你好", result)
        val request = client.requests.last()
        assertEquals("POST", request.method)
        assertEquals(key, request.headers["X-Goog-API-Key"])
        val payload = JSONArray(request.body!!)
        assertEquals("en", payload.getJSONArray(0).getString(1))
        assertEquals("zh-CN", payload.getJSONArray(0).getString(2))
    }

    @Test
    fun deepLUsesTheSelectedPlanAndKeepsTheKeyOutOfTheBody() {
        val client = RecordingHttpClient(
            HttpResponse(200, "{\"translations\":[{\"text\":\"你好\"}]}")
        )

        val result = DeepLTranslator(client).translate(
            "hello",
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
