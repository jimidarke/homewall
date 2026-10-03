package io.haku.tablet.data

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Axis ticks drawn per chart: more than a 1000 dp panel can label at 16 sp anyway. */
private const val MAX_TICKS = 24

/**
 * Parses an `/api/detail/<id>` body (contract section 1). Tolerant: each block is parsed on its own, and an
 * unknown or malformed one is skipped, so one bad block never costs the panel the rest. A block that would
 * show nothing (no items, no series and no `empty` text) is skipped too. The contract's clamps apply
 * (6 stats, 4 series, 2000 chart points, 8 days, 5 forecast days, 30 rows, 12 hourly cells). A block's `col`
 * (0 or 1, clamped; absent or not a whole number is 0) picks the column it is listed in. Throws only when
 * [body] is not a JSON object.
 */
fun parseDetail(body: String): Detail {
    val root = HubJson.json.parseToJsonElement(body) as? JsonObject
        ?: throw IllegalArgumentException("detail is not a JSON object")
    val parsed = root.array("blocks").orEmpty().mapNotNull { el ->
        runCatching {
            (el as? JsonObject)?.let { o -> parseBlock(o)?.let { it to (o.int("col") ?: 0).coerceIn(0, 1) } }
        }.getOrNull()
    }
    return Detail(
        v = root.int("v") ?: 1,
        id = root.str("id"),
        title = root.str("title"),
        ts = root.long("ts") ?: 0L,
        note = root.strOrNull("note")?.takeIf { it.isNotBlank() },
        blocks = parsed.filter { it.second == 0 }.map { it.first },
        right = parsed.filter { it.second == 1 }.map { it.first },
    )
}

private fun parseBlock(o: JsonObject): DetailBlock? = when (o.str("type")) {
    "stats" -> statItems(o.array("items"), MAX_STATS).takeIf { it.isNotEmpty() }?.let { DetailBlock.Stats(it) }
    "days" -> statItems(o.array("items"), MAX_DAYS).takeIf { it.isNotEmpty() }?.let { DetailBlock.Days(it) }
    "chart" -> parseChart(o)
    "forecast" -> parseForecast(o)
    "rows" -> parseRows(o)
    "now" -> parseNow(o)
    "hourly" -> parseHourly(o)
    else -> null
}

/** Items need a label and a value; the optional `sub` is a null when absent. */
private fun statItems(arr: JsonArray?, max: Int): List<StatItem> =
    arr.orEmpty().mapNotNull { el ->
        val o = el as? JsonObject ?: return@mapNotNull null
        StatItem(o.strOrNull("label") ?: return@mapNotNull null, o.strOrNull("value") ?: return@mapNotNull null, o.sub())
    }.take(max)

private fun parseForecast(o: JsonObject): DetailBlock.Forecast? {
    val days = o.array("days").orEmpty().mapNotNull { el ->
        val d = el as? JsonObject ?: return@mapNotNull null
        ForecastDay(
            label = d.strOrNull("label") ?: return@mapNotNull null,
            glyph = d.str("glyph"),
            cond = d.str("cond"),
            hi = d.opt("hi"),
            lo = d.opt("lo"),
            sub = d.sub(),
        )
    }.take(MAX_FORECAST)
    return days.takeIf { it.isNotEmpty() }?.let { DetailBlock.Forecast(it, compact = o.str("style") == "compact") }
}

/** The hero needs its temperature; everything else is optional and a blank one is null. */
private fun parseNow(o: JsonObject): DetailBlock.Now? {
    val temp = o.opt("temp") ?: return null
    return DetailBlock.Now(o.opt("glyph"), temp, o.opt("cond"), o.opt("hilo"), o.sub())
}

/** Cells need a label and a temperature. */
private fun parseHourly(o: JsonObject): DetailBlock.Hourly? {
    val cells = o.array("items").orEmpty().mapNotNull { el ->
        val c = el as? JsonObject ?: return@mapNotNull null
        HourCell(
            label = c.opt("label") ?: return@mapNotNull null,
            glyph = c.opt("glyph"),
            temp = c.opt("temp") ?: return@mapNotNull null,
            sub = c.sub(),
        )
    }.take(MAX_HOURLY)
    return cells.takeIf { it.isNotEmpty() }?.let { DetailBlock.Hourly(it) }
}

private fun parseRows(o: JsonObject): DetailBlock.Rows? {
    val items = o.array("items").orEmpty().mapNotNull { el ->
        val r = el as? JsonObject ?: return@mapNotNull null
        RowItem(
            glyph = r.opt("glyph"),
            tone = r.opt("tone"),
            label = r.strOrNull("label") ?: return@mapNotNull null,
            value = r.strOrNull("value") ?: return@mapNotNull null,
            sub = r.sub(),
        )
    }.take(MAX_ROWS)
    return items.takeIf { it.isNotEmpty() }?.let { DetailBlock.Rows(o.opt("title"), it) }
}

private fun parseChart(o: JsonObject): DetailBlock.Chart? {
    val empty = o.opt("empty")
    val seriesJson = o.array("series")
    if (seriesJson == null && empty == null) return null   // nothing to plot and nothing to say
    val count = (o.int("count") ?: 0).coerceAtLeast(0)
    var budget = MAX_CHART_POINTS
    val series = seriesJson.orEmpty().mapNotNull { it as? JsonObject }.take(MAX_SERIES).map { s ->
        val runs = parseRuns(s.array("runs"), count, budget)
        budget -= runs.sumOf { it.v.size }
        Series(label = s.str("label"), tone = s.opt("tone"), fill = s.bool("fill"), runs = runs)
    }
    val xTicks = o.obj("x")?.array("ticks").orEmpty().mapNotNull { el ->
        val t = el as? JsonObject ?: return@mapNotNull null
        XTick(t.int("i") ?: return@mapNotNull null, t.str("label"), t.bool("strong"))
    }.take(MAX_TICKS)
    return DetailBlock.Chart(
        title = o.opt("title"),
        start = o.long("start") ?: 0L,
        step = o.long("step") ?: 0L,
        count = count,
        series = series,
        xTicks = xTicks,
        y = parseYAxis(o.obj("y")),
        empty = empty,
    )
}

/** Null (the tablet then scales from the data) when [y] is missing, has no numeric min and max, or `max <= min`. */
private fun parseYAxis(y: JsonObject?): YAxis? {
    val min = y?.float("min") ?: return null
    val max = y.float("max") ?: return null
    if (max <= min) return null
    val ticks = y.array("ticks").orEmpty().mapNotNull { el ->
        val t = el as? JsonObject ?: return@mapNotNull null
        YTick(t.float("v") ?: return@mapNotNull null, t.str("label"))
    }.take(MAX_TICKS)
    return YAxis(min, max, ticks)
}

/**
 * The runs of one series over [count] buckets, spending at most [budget] points. A bucket outside
 * `[0, count)` is clipped, and a non-number (string, boolean, null) is a gap that splits its run in two.
 * A run with no usable value is dropped.
 */
internal fun parseRuns(arr: JsonArray?, count: Int, budget: Int): List<Run> {
    val out = ArrayList<Run>()
    var left = budget
    for (el in arr.orEmpty()) {
        if (left <= 0) break
        val run = el as? JsonObject ?: continue
        val first = run.int("i") ?: continue
        val values = run.array("v") ?: continue
        var from = 0                                // bucket of the first value in `cur`
        var cur = FloatArray(0)
        var n = 0
        for ((k, e) in values.withIndex()) {
            val bucket = first.toLong() + k         // a Long, so a huge `i` cannot wrap around
            if (bucket >= count || left <= 0) break
            val f = (e as? JsonPrimitive)?.finiteFloatOrNull()
            if (bucket < 0 || f == null) {          // clipped or a gap: close the run so far
                if (n > 0) out += Run(from, cur.copyOf(n))
                n = 0
                continue
            }
            if (n == 0) from = bucket.toInt()
            if (n == cur.size) cur = cur.copyOf(maxOf(8, n * 2))
            cur[n++] = f
            left--
        }
        if (n > 0) out += Run(from, cur.copyOf(n))
    }
    return out
}

/** An optional string: null when absent or blank, so the UI never reserves a line for it. */
private fun JsonObject.opt(k: String): String? = strOrNull(k)?.takeIf { it.isNotBlank() }

private fun JsonObject.sub(): String? = opt("sub")
