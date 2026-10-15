package io.haku.tablet.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.util.concurrent.TimeUnit

sealed interface Fetch<out T> {
    data class Ok<T>(val value: T) : Fetch<T>
    data class HttpError(val code: Int) : Fetch<Nothing>
    data class NetworkError(val message: String) : Fetch<Nothing>
    data class ParseError(val message: String) : Fetch<Nothing>
}

/** Why a fetch failed, as the offline banner and the `err=` of a log line both show it: "http 502", "network: …". */
fun Fetch<*>.describe(): String = when (this) {
    is Fetch.Ok -> "ok"
    is Fetch.HttpError -> "http $code"
    is Fetch.NetworkError -> "network: $message"
    is Fetch.ParseError -> "parse: $message"
}

/**
 * Read-only client for the haku-sidecar. Every call returns a [Fetch]; nothing throws.
 *
 * [layout], when set, is sent as `?layout=` on every request so the sidecar tailors config and
 * state to this device. Null gives the plain responses the Roku gets.
 */
class SidecarClient(
    private val base: String,
    private val layout: String? = null,
    private val http: OkHttpClient = defaultClient(),
) : HubSource {
    override suspend fun config(): Fetch<HubConfig> =
        get(url("api/config")) { HubJson.parseConfig(it.decodeToString()) }

    override suspend fun state(): Fetch<HubState> =
        get(url("api/state")) { HubJson.parseState(it.decodeToString()) }

    override suspend fun backgrounds(): Fetch<List<String>> =
        get(url("api/backgrounds")) { parseBackgrounds(it.decodeToString()) }

    override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> {
        val url = url("api/background", name) {
            addQueryParameter("w", w.toString())
            addQueryParameter("h", h.toString())
            addQueryParameter("fit", fit)
            if (blur > 0) addQueryParameter("blur", blur.toString())
        }
        return get(url) { it }
    }

    /** A cold detail call (HA statistics) can take a few seconds, so it gets longer timeouts than the 1 s polls. */
    private val detailHttp: OkHttpClient by lazy {
        http.newBuilder().readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS).build()
    }

    override suspend fun detail(id: String): Fetch<Detail> =
        get(url("api/detail", id), detailHttp) { parseDetail(it.decodeToString()) }

    /** Built with [HttpUrl] so image names and query values are percent-encoded properly. */
    private fun url(path: String, segment: String? = null, query: HttpUrl.Builder.() -> Unit = {}): HttpUrl =
        base.toHttpUrl().newBuilder().apply {
            addPathSegments(path)
            if (segment != null) addPathSegment(segment)
            if (layout != null) addQueryParameter("layout", layout)
            query()
        }.build()

    private suspend fun <T> get(url: HttpUrl, client: OkHttpClient = http, parse: (ByteArray) -> T): Fetch<T> =
        withContext(Dispatchers.IO) {
            val body = try {
                client.newCall(Request.Builder().url(url).build()).execute().use { resp ->
                    if (!resp.isSuccessful) return@withContext Fetch.HttpError(resp.code)
                    resp.body?.bytes() ?: ByteArray(0)
                }
            } catch (e: IOException) {
                return@withContext Fetch.NetworkError(e.message ?: e.javaClass.simpleName)
            }
            try {
                Fetch.Ok(parse(body))
            } catch (e: Exception) {   // SerializationException / IllegalArgumentException
                Fetch.ParseError(e.message?.take(120) ?: e.javaClass.simpleName)
            }
        }

    companion object {
        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .callTimeout(8, TimeUnit.SECONDS)
            .build()
    }
}

/** `{"images":[{"name":…}]}` to names. Entries without a name are skipped; no `images` key is empty. */
private fun parseBackgrounds(body: String): List<String> {
    val root = HubJson.json.parseToJsonElement(body) as? JsonObject
        ?: throw IllegalArgumentException("backgrounds is not a JSON object")
    val images = root["images"] as? JsonArray ?: return emptyList()
    return images.mapNotNull { ((it as? JsonObject)?.get("name") as? JsonPrimitive)?.contentOrNull }
}
