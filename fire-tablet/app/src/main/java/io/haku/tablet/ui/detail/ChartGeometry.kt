package io.haku.tablet.ui.detail

import io.haku.tablet.data.DetailBlock
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/*
 * Chart geometry, kept pure (no Compose types) so the mapping from buckets and values to pixels is unit
 * tested. ChartBlock turns the result into Paths once per size change and draws them.
 */

/** Pixels reserved around the plot for the axis labels. */
data class PlotInsets(val left: Float, val top: Float, val right: Float, val bottom: Float)

/**
 * One series in pixels. Every `FloatArray` is x,y pairs.
 * - [lines]: one polyline per run of two or more buckets. Runs are never joined, so a gap stays a gap.
 * - [dots]: the points of one-bucket runs, which have no line to draw.
 * - [fills]: one closed polygon per line (its points, then down to the baseline and back); empty unless the series fills.
 */
class SeriesGeometry(val lines: List<FloatArray>, val dots: FloatArray, val fills: List<FloatArray>)

/**
 * A tick's pixel position along its axis (y for [ChartGeometry.yTicks], x for [ChartGeometry.xTicks]), and its
 * text. A [strong] x tick is the chart's "Now".
 */
data class AxisTick(val pos: Float, val label: String, val strong: Boolean = false)

/**
 * A chart laid out in a box: the plot rectangle ([left], [top], [right], [bottom]), the value range it shows
 * ([min] to [max]), the [baseline] fills close to, and the series and ticks in pixels. [yTicks] have empty labels
 * when the scale was derived from the data, since the sidecar then gave nothing to print.
 */
class ChartGeometry(
    val left: Float, val top: Float, val right: Float, val bottom: Float,
    val min: Float, val max: Float,
    val baseline: Float,
    val series: List<SeriesGeometry>,
    val yTicks: List<AxisTick>,
    val xTicks: List<AxisTick>,
)

/** The centre of bucket [i] of [count] equal buckets spanning [left] to [right]. */
fun bucketX(i: Int, count: Int, left: Float, right: Float): Float =
    left + (i + 0.5f) / count.coerceAtLeast(1) * (right - left)

/** The y of [v] on a scale from [min] (at [bottom]) to [max] (at [top]); values outside the scale clamp to its ends. */
fun valueY(v: Float, min: Float, max: Float, top: Float, bottom: Float): Float {
    if (max <= min) return bottom
    val t = (v.coerceIn(min, max) - min) / (max - min)
    return bottom - t * (bottom - top)
}

/** A "nice" axis: [min] and [max] are multiples of [step], which is 1, 2, 2.5 or 5 times a power of ten. */
data class NiceScale(val min: Float, val max: Float, val step: Float) {
    /** Every gridline value from [min] to [max]. */
    fun ticks(): List<Float> {
        val n = Math.round((max.toDouble() - min) / step).toInt()
        return List(n + 1) { (min.toDouble() + it * step.toDouble()).toFloat() }
    }
}

/**
 * A nice range covering [lo] to [hi] (in either order) with about [intervals] gridline gaps. A flat range
 * (including a single value) is widened so the scale is never empty: 0 gives 0..1, any other value gets 10%
 * each side.
 */
fun niceScale(lo: Float, hi: Float, intervals: Int = 4): NiceScale {
    var a = min(lo, hi).toDouble()
    var b = max(lo, hi).toDouble()
    if (b == a) {
        if (a == 0.0) b = 1.0 else { val pad = abs(a) * 0.1; a -= pad; b += pad }
    }
    val step = niceStep((b - a) / intervals.coerceAtLeast(1))
    // The epsilon keeps a value that is already on a gridline (floating point noise) from adding a whole step.
    val min = floor(a / step + 1e-9) * step
    val max = ceil(b / step - 1e-9) * step
    return NiceScale(min.toFloat(), max.toFloat(), step.toFloat())
}

/** The smallest of 1, 2, 2.5, 5, 10 times a power of ten that is at least [raw]. */
private fun niceStep(raw: Double): Double {
    val exp = floor(log10(raw))
    val base = 10.0.pow(exp)
    val f = raw / base
    val nice = when {
        f <= 1.0 + 1e-9 -> 1.0
        f <= 2.0 + 1e-9 -> 2.0
        f <= 2.5 + 1e-9 -> 2.5
        f <= 5.0 + 1e-9 -> 5.0
        else -> 10.0
    }
    return nice * base
}

/**
 * The range a chart with no usable `y` is drawn over, derived from its data ([niceScale]). It reaches down to
 * zero when any series fills, since an area chart that does not start at zero misleads. With no data at all any
 * scale will do, as nothing is drawn on it.
 */
internal fun dataScale(chart: DetailBlock.Chart): NiceScale {
    var lo = Float.POSITIVE_INFINITY
    var hi = Float.NEGATIVE_INFINITY
    for (s in chart.series) for (r in s.runs) for (v in r.v) {
        lo = min(lo, v)
        hi = max(hi, v)
    }
    if (lo > hi) return niceScale(0f, 1f)
    if (chart.series.any { it.fill }) {
        lo = min(lo, 0f)
        hi = max(hi, 0f)
    }
    return niceScale(lo, hi)
}

/**
 * Lays [chart] out in a [width] by [height] box with [insets] left for labels. Bucket i sits at the centre of
 * its slot of [DetailBlock.Chart.count]; values clamp into the scale. A run of one bucket is a dot, a longer
 * one a polyline (and, for a filling series, a polygon closed to the baseline: the zero line, kept inside the
 * plot). Y ticks outside the range are dropped. X ticks sit on their bucket's centre, so a tick is exactly
 * under its bucket's point.
 */
fun chartGeometry(chart: DetailBlock.Chart, width: Float, height: Float, insets: PlotInsets): ChartGeometry {
    val left = insets.left
    val top = insets.top
    val right = (width - insets.right).coerceAtLeast(left)
    val bottom = (height - insets.bottom).coerceAtLeast(top)

    // The scale and its gridlines: the sidecar's (with its labels), else derived from the data (unlabelled).
    val axis = chart.y
    val derived = if (axis == null) dataScale(chart) else null
    val min = axis?.min ?: derived!!.min
    val max = axis?.max ?: derived!!.max
    val ticks = axis?.ticks?.map { it.v to it.label } ?: derived!!.ticks().map { it to "" }
    val baseline = valueY(0f, min, max, top, bottom)

    val series = chart.series.map { s ->
        val lines = ArrayList<FloatArray>()
        val fills = ArrayList<FloatArray>()
        var dots = FloatArray(0)
        for (run in s.runs) {
            if (run.v.isEmpty()) continue
            if (run.v.size == 1) {
                dots += floatArrayOf(bucketX(run.i, chart.count, left, right), valueY(run.v[0], min, max, top, bottom))
                continue
            }
            val line = FloatArray(run.v.size * 2)
            for (k in run.v.indices) {
                line[2 * k] = bucketX(run.i + k, chart.count, left, right)
                line[2 * k + 1] = valueY(run.v[k], min, max, top, bottom)
            }
            lines += line
            if (s.fill) {
                val n = line.size
                fills += line.copyOf(n + 4).also {
                    it[n] = line[n - 2]; it[n + 1] = baseline
                    it[n + 2] = line[0]; it[n + 3] = baseline
                }
            }
        }
        SeriesGeometry(lines, dots, fills)
    }

    val eps = (max - min) * 1e-4f
    val yTicks = ticks.filter { (v, _) -> v >= min - eps && v <= max + eps }
        .map { (v, label) -> AxisTick(valueY(v, min, max, top, bottom), label) }
    val xTicks = chart.xTicks.filter { it.i in 0 until chart.count }
        .map { AxisTick(bucketX(it.i, chart.count, left, right), it.label, it.strong) }

    return ChartGeometry(left, top, right, bottom, min, max, baseline, series, yTicks, xTicks)
}

/** One x label's horizontal extent in pixels, and whether it must be kept ([strong], the chart's "Now"). */
data class LabelSpan(val start: Float, val width: Float, val strong: Boolean)

/**
 * Which of [spans] (in left to right order) get drawn. A strong label always does, unless an earlier strong one
 * already overlaps it. Every other label is then drawn left to right as long as it keeps [gap] clear of the labels
 * drawn so far, strong ones included: so "Now" is never the one dropped when a neighbour is in its way.
 */
fun thinLabels(spans: List<LabelSpan>, gap: Float): List<Boolean> {
    val keep = BooleanArray(spans.size)
    fun clear(i: Int) = spans.indices.none { j ->
        keep[j] && spans[i].start < spans[j].start + spans[j].width + gap &&
            spans[j].start < spans[i].start + spans[i].width + gap
    }
    for (i in spans.indices) if (spans[i].strong && clear(i)) keep[i] = true
    for (i in spans.indices) if (!spans[i].strong && clear(i)) keep[i] = true
    return keep.toList()
}
