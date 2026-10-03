package io.haku.tablet.data

import androidx.compose.runtime.Immutable

/*
 * The /api/detail/<id> payload (docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md section 1),
 * parsed by [parseDetail]. Every string is display-ready and shown verbatim; only chart values are numbers.
 * The model is already clamped and cleaned, so the UI never validates it again.
 */

/**
 * One module's detail: its [blocks] in display order, plus an optional [note] shown small under them. A block
 * the sidecar placed in column 1 (`"col": 1`) is in [right] instead; the panel draws two columns only when both
 * lists have blocks, and otherwise stacks them as one.
 */
@Immutable
data class Detail(
    val v: Int,
    val id: String,
    val title: String,
    /** Epoch seconds when the sidecar built it. */
    val ts: Long,
    val note: String?,
    val blocks: List<DetailBlock>,
    val right: List<DetailBlock> = emptyList(),
)

@Immutable
sealed interface DetailBlock {
    /** A row of up to [MAX_STATS] label/value pairs. */
    @Immutable
    data class Stats(val items: List<StatItem>) : DetailBlock

    /**
     * A time-series line chart over [count] uniform buckets of [step] seconds starting at [start]. [y] is null
     * when the sidecar sent no usable scale, and the tablet then derives one from the data. [empty] is shown
     * instead of the plot when no series has a run.
     */
    @Immutable
    data class Chart(
        val title: String?,
        val start: Long,
        val step: Long,
        val count: Int,
        val series: List<Series>,
        val xTicks: List<XTick>,
        val y: YAxis?,
        val empty: String?,
    ) : DetailBlock {
        /** True when no series has any point, so there is nothing to plot. */
        val isEmpty: Boolean get() = series.all { it.runs.isEmpty() }
    }

    /** A strip of per-day totals, oldest first. */
    @Immutable
    data class Days(val items: List<StatItem>) : DetailBlock

    /** The next days. [compact] is the weather panel's one-line-a-day list; otherwise a column per day. */
    @Immutable
    data class Forecast(val days: List<ForecastDay>, val compact: Boolean = false) : DetailBlock

    /** The weather panel's hero: the big temperature with its glyph, condition, today's high/low and a freshness line. */
    @Immutable
    data class Now(
        val glyph: String?,
        val temp: String,
        val cond: String?,
        val hilo: String?,
        val sub: String?,
    ) : DetailBlock

    /** A strip of hour cells, soonest first. */
    @Immutable
    data class Hourly(val items: List<HourCell>) : DetailBlock

    @Immutable
    data class Rows(val title: String?, val items: List<RowItem>) : DetailBlock
}

/** A label, its value and an optional second line. Used by both `stats` and `days`. */
@Immutable
data class StatItem(val label: String, val value: String, val sub: String? = null)

/** [tone] is the sidecar's token key, resolved by `toneColor`. */
@Immutable
data class Series(val label: String, val tone: String?, val fill: Boolean, val runs: List<Run>)

/**
 * A contiguous stretch of real data: [v] holds the values of buckets [i] until `i + v.size`. Non-empty and
 * gap-free after parsing. Equality is by content, so a re-fetch of the same data is `==` and skips recomposition.
 */
@Immutable
class Run(val i: Int, val v: FloatArray) {
    val end: Int get() = i + v.size

    override fun equals(other: Any?): Boolean = other is Run && i == other.i && v.contentEquals(other.v)
    override fun hashCode(): Int = 31 * i + v.contentHashCode()
    override fun toString(): String = "Run(i=$i, v=${v.contentToString()})"
}

/** A [strong] tick (the chart's "Now") draws a firmer line and its label in full ink, and never loses its label to a neighbour. */
@Immutable
data class XTick(val i: Int, val label: String, val strong: Boolean = false)

@Immutable
data class YTick(val v: Float, val label: String)

/** [max] is always greater than [min]. [ticks] may be empty (a plain scale with no labels). */
@Immutable
data class YAxis(val min: Float, val max: Float, val ticks: List<YTick>)

/** [glyph] is an MDI `weather-*` name ("" if absent; the block then draws the weather default). */
@Immutable
data class ForecastDay(
    val label: String,
    val glyph: String,
    val cond: String,
    val hi: String? = null,
    val lo: String? = null,
    val sub: String? = null,
)

/** One cell of an `hourly` strip: [label] ("4 PM") and [temp] ("7°") always, [glyph] and [sub] (the rain chance) when sent. */
@Immutable
data class HourCell(val label: String, val glyph: String?, val temp: String, val sub: String?)

/** [glyph] and [tone] are the sidecar's keys, both optional. */
@Immutable
data class RowItem(
    val glyph: String?,
    val tone: String?,
    val label: String,
    val value: String,
    val sub: String? = null,
)

/** The contract's clamps (section 1), applied by [parseDetail]. */
const val MAX_STATS = 6
const val MAX_SERIES = 4
const val MAX_CHART_POINTS = 2000
const val MAX_DAYS = 8
const val MAX_FORECAST = 5
const val MAX_ROWS = 30
const val MAX_HOURLY = 12
