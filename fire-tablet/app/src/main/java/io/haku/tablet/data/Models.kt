package io.haku.tablet.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull

/*
 * Mirrors of the haku-sidecar contract (sidecar/README.md):
 *   /api/config -> HubConfig (module descriptors + grid)
 *   /api/state  -> HubState  (per-feedKey values; the sidecar owns all display formatting)
 * Unknown keys are ignored so a newer sidecar never breaks an older tablet build.
 */

@Serializable
data class Grid(val cols: Int = 4, val rows: Int = 3)

@Serializable
data class TileSpec(
    val type: String = "value",
    val col: Int = 0,
    val row: Int = 0,
    val w: Int = 1,
    val h: Int = 1,
    val dropHeaders: Boolean = false,
)

@Serializable
data class ModuleDesc(
    val id: String,
    val kind: String,
    val title: String = "",
    val feedKey: String? = null,
    val refreshMs: Long? = null,
    val tile: TileSpec = TileSpec(),
) {
    /** Key into /api/state, same rule as the sidecar's compose_state. */
    val key: String get() = feedKey ?: id
}

/** Photo backdrop behind the glass cards (`background` block of `?layout=tablet`). */
@Serializable
data class BackgroundSpec(val enabled: Boolean = false, val intervalMs: Long = 180_000)

/** Overnight dim window, "HH:mm" local strings; absent block means never dim. */
@Serializable
data class NightDim(val start: String = "", val end: String = "", val brightness: Float = 0.15f)

@Serializable
data class HubConfig(
    val grid: Grid = Grid(),
    val modules: List<ModuleDesc> = emptyList(),
    val background: BackgroundSpec = BackgroundSpec(),
    val nightDim: NightDim? = null,
)

/** [glyph] is an MDI name ("" when absent); [level] is 0..100 for energy/water/gas, else null. */
data class TileValues(
    val hero: String,
    val sub: String,
    val detail: String,
    val severity: String,
    val glyph: String = "",
    val active: Boolean = false,
    val level: Int? = null,
)

/** [dot] is the Roku-format `0xRRGGBBAA` colour (calendar rows); [whenTs] is the event's epoch seconds. */
data class AgendaItem(
    val kind: String,
    val title: String,
    val sub: String,
    val time: String,
    val severity: String,
    val glyph: String = "",
    val dot: String = "",
    val whenTs: Long? = null,
)

/** [state] is always `open`, `closed` or `unknown`. */
data class Door(
    val id: String,
    val label: String,
    val state: String,
    val age: String,
    val severity: String,
    val glyph: String,
)

/** [mode] is `idle | running | overtime | done | done_calm`; [leds] is 0..4; [status] is sidecar-formatted. */
data class Machine(
    val id: String,
    val label: String,
    val color: String,
    val mode: String,
    val leds: Int,
    val status: String,
    val glyph: String,
    val stale: Boolean,
)

/** The /api/state snapshot. Kept as raw JSON: each module's value shape differs, tiles share one. */
class HubState(private val root: JsonObject) {
    val ts: Long? get() = (root["ts"] as? JsonPrimitive)?.longOrNull

    fun tile(key: String): TileValues? {
        val t = (root[key] as? JsonObject)?.get("tile") as? JsonObject ?: return null
        return TileValues(
            hero = t.str("hero"),
            sub = t.str("sub"),
            detail = t.str("detail"),
            severity = t.str("severity").ifEmpty { "normal" },
            glyph = t.str("glyph"),
            active = t.bool("active"),
            level = t.int("level")?.coerceIn(0, 100),
        )
    }

    /** True only when the module's `stale` is a JSON `true`; false when absent. */
    fun stale(key: String): Boolean = (root[key] as? JsonObject)?.bool("stale") ?: false

    /**
     * The module's `error` string, or null when it has none. The sidecar sends `{"error": "..."}` in place of
     * a module whose update threw, so the module has no tile that poll.
     */
    fun error(key: String): String? =
        ((root[key] as? JsonObject)?.get("error") as? JsonPrimitive)?.takeIf { it.isString }?.content

    fun items(key: String, dropHeaders: Boolean = false): List<AgendaItem> {
        val arr = (root[key] as? JsonObject)?.get("items") as? JsonArray ?: return emptyList()
        return arr.mapNotNull { it as? JsonObject }
            .map {
                AgendaItem(
                    kind = it.str("kind").ifEmpty { "event" },
                    title = it.str("title"),
                    sub = it.str("sub"),
                    time = it.str("time"),
                    severity = it.str("severity").ifEmpty { "normal" },
                    glyph = it.str("glyph"),
                    dot = it.str("dot"),
                    whenTs = it.long("when"),
                )
            }
            .filter { !(dropHeaders && it.kind == "header") }
    }

    /** Null when [key] has no `doors` array, so the card can fall back to a plain value tile. */
    fun doors(key: String): List<Door>? {
        val arr = (root[key] as? JsonObject)?.get("doors") as? JsonArray ?: return null
        return arr.mapNotNull { it as? JsonObject }.map {
            Door(
                id = it.str("id"),
                label = it.str("label"),
                state = it.str("state").let { s -> if (s == "open" || s == "closed") s else "unknown" },
                age = it.str("age"),
                severity = it.str("severity").ifEmpty { "normal" },
                glyph = it.str("glyph"),
            )
        }
    }

    /** Null when [key] has no `machines` array, so the card can fall back to a plain value tile. */
    fun laundry(key: String): List<Machine>? {
        val arr = (root[key] as? JsonObject)?.get("machines") as? JsonArray ?: return null
        return arr.mapNotNull { it as? JsonObject }.map {
            Machine(
                id = it.str("id"),
                label = it.str("label"),
                color = it.str("color"),
                mode = it.str("mode"),
                leds = (it.int("leds") ?: 0).coerceIn(0, 4),
                status = it.str("status"),
                glyph = it.str("glyph"),
                stale = it.bool("stale"),
            )
        }
    }

    private fun JsonObject.str(k: String): String =
        (this[k] as? JsonPrimitive)?.contentOrNull ?: ""

    /** True only for a JSON boolean `true`; the string "true", numbers and null are false. */
    private fun JsonObject.bool(k: String): Boolean =
        (this[k] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull ?: false

    /** A JSON integer, or null for a missing key, a string, a fraction or anything non-numeric. */
    private fun JsonObject.long(k: String): Long? =
        (this[k] as? JsonPrimitive)?.takeIf { !it.isString }?.longOrNull

    /** Like [long], saturated into the Int range so callers can clamp to their own bounds. */
    private fun JsonObject.int(k: String): Int? =
        long(k)?.coerceIn(Int.MIN_VALUE.toLong(), Int.MAX_VALUE.toLong())?.toInt()
}

object HubJson {
    val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    fun parseConfig(body: String): HubConfig = json.decodeFromString(HubConfig.serializer(), body)

    fun parseState(body: String): HubState =
        HubState(json.parseToJsonElement(body) as? JsonObject
            ?: throw IllegalArgumentException("state is not a JSON object"))
}
