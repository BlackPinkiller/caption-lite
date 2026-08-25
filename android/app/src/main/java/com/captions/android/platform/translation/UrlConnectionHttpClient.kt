package com.captions.android.platform.translation

import com.captions.android.ports.HttpClient
import com.captions.android.ports.HttpRequest
import com.captions.android.ports.HttpResponse
import java.net.HttpURLConnection
import java.net.URL

class UrlConnectionHttpClient : HttpClient {
    override fun execute(request: HttpRequest): HttpResponse {
        val connection = (URL(request.url).openConnection() as HttpURLConnection).apply {
            requestMethod = request.method
            connectTimeout = request.timeoutMillis
            readTimeout = request.timeoutMillis
            instanceFollowRedirects = true
            request.headers.forEach(::setRequestProperty)
            if (request.body != null) {
                doOutput = true
                outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(request.body) }
            }
        }
        return try {
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            HttpResponse(status, stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty())
        } finally {
            connection.disconnect()
        }
    }
}
