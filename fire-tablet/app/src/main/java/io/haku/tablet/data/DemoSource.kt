package io.haku.tablet.data

import java.io.IOException

/**
 * Debug-only [HubSource]: config and state come from canned JSON (assets `demo/`), so every
 * card state can be screenshotted without the house doing anything. Backgrounds still come from
 * [real], so the photo path is exercised for real.
 *
 * [scenario] is `quiet`, `busy`, `alert`, `cycle` to rotate through them every 10 s, or `offline`: the quiet
 * state for 5 s after construction, then a network error on every state fetch (the config keeps working),
 * so the lagging dot, the offline banner and the dimmed cards show up on their real timers.
 *
 * `degraded` is the quiet state for 5 s too, then the same house with the water meter out (`degraded.json`:
 * water `stale` with a `-- L/min` hero), so the water card holds its quiet reading, greyed "as of" the last
 * quiet poll, and the header reads "degraded · Water".
 */
class DemoSource(
    private val read: (String) -> String,
    private val scenario: String,
    private val real: HubSource,
    private val clock: () -> Long = System::currentTimeMillis,
    private val detailVariant: String? = null,
) : HubSource {
    private val startedAt = clock()

    override suspend fun config(): Fetch<HubConfig> = load("demo/config.json", HubJson::parseConfig)

    override suspend fun state(): Fetch<HubState> =
        if (scenario == "offline" && clock() - startedAt >= OFFLINE_AFTER_MS) {
            Fetch.NetworkError("demo offline")
        } else {
            load("demo/${current()}.json", HubJson::parseState)
        }

    override suspend fun backgrounds(): Fetch<List<String>> = real.backgrounds()

    override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> =
        real.background(name, w, h, fit, blur)

    /**
     * `demo/detail_<id>.json`; a missing asset is a 404, like a kind the sidecar has no detail for. With a
     * [detailVariant] (`--es demo_detail nofc`), `demo/detail_<id>_<variant>.json` is read first when it exists.
     */
    override suspend fun detail(id: String): Fetch<Detail> {
        if (!isPlainName(id)) return Fetch.HttpError(404)
        val variant = detailVariant?.takeIf(::isPlainName)
        val body = try {
            variant?.let { v -> try { read("demo/detail_${id}_$v.json") } catch (_: IOException) { null } }
                ?: read("demo/detail_$id.json")
        } catch (e: IOException) {
            return Fetch.HttpError(404)
        }
        return try {
            Fetch.Ok(parseDetail(body))
        } catch (e: Exception) {
            Fetch.ParseError(e.message?.take(120) ?: e.javaClass.simpleName)
        }
    }

    private fun isPlainName(s: String) = s.isNotEmpty() && s.all { it.isLetterOrDigit() || it == '_' || it == '-' }

    private fun current(): String = when (scenario) {
        "cycle" -> CYCLE[((clock() / CYCLE_MS) % CYCLE.size).toInt()]
        "offline" -> "quiet"
        "degraded" -> if (clock() - startedAt >= OFFLINE_AFTER_MS) "degraded" else "quiet"
        else -> scenario
    }

    private fun <T> load(path: String, parse: (String) -> T): Fetch<T> =
        try {
            Fetch.Ok(parse(read(path)))
        } catch (e: Exception) {   // missing asset, SerializationException, IllegalArgumentException
            Fetch.ParseError(e.message?.take(120) ?: e.javaClass.simpleName)
        }

    private companion object {
        val CYCLE = listOf("quiet", "busy", "alert")
        const val CYCLE_MS = 10_000L
        /** How long `offline` and `degraded` serve the quiet state before their fault starts. */
        const val OFFLINE_AFTER_MS = 5_000L
    }
}
