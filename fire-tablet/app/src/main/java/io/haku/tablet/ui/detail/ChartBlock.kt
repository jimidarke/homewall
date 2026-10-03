package io.haku.tablet.ui.detail

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.haku.tablet.data.DetailBlock
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import kotlin.math.max
import kotlin.math.min

private val LineWidth = 2.dp
private val DotRadius = 3.dp
private val GridWidth = 1.dp

/** Gap between the plot and its labels. */
private val AxisGap = 8.dp

/** Room kept around the plot when it has no labels on that side, so a line at the edge is not clipped. */
private val EdgePad = 4.dp

private val Gridline = Haku.ink.copy(alpha = 0.10f)
private val DayLine = Haku.ink.copy(alpha = 0.06f)

/** The "Now" tick: firmer than a day line, and its label in full ink. */
private val NowLine = Haku.ink.copy(alpha = 0.35f)
private const val NOW_LINE_SCALE = 1.5f

/** The area under a filling series fades from this alpha at its peak to nothing at the baseline. */
private const val FILL_ALPHA = 0.30f

private val SwatchWidth = 18.dp
private val SwatchHeight = 4.dp

/** Space between the title/legend row and the plot. */
private val HeaderGap = 6.dp

/**
 * A line chart over uniform buckets (contract section 1). An optional title sits above it, with a legend (a
 * swatch and label per series) at its right once there are two or more series. Faint gridlines run at the
 * y ticks, whose labels go in the left gutter; x labels (the weekday) sit under the plot, to the right of a
 * faint line at each tick. A strong tick (the weather chart's "Now") has a firmer line and its label in full
 * ink, and keeps its label when a neighbour would overlap it. Each series is a 2 dp line in its tone, with a gradient fill when it asks for one;
 * runs are separate paths, so a gap is never bridged, and a one-bucket run is a dot. With no data it shows
 * the sidecar's `empty` text centred instead. It takes whatever height it is given, and does not animate.
 */
@Composable
fun ChartBlock(chart: DetailBlock.Chart, modifier: Modifier = Modifier) {
    val showLegend = chart.series.size >= 2
    Column(modifier) {
        if (chart.title != null || showLegend) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    chart.title.orEmpty(), style = HakuType.cardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                if (showLegend) Legend(chart)
            }
            Spacer(Modifier.height(HeaderGap))
        }
        if (chart.isEmpty && chart.empty != null) {
            Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                Text(chart.empty, style = HakuType.sub, color = Haku.inkMuted)
            }
        } else {
            Plot(chart, Modifier.fillMaxWidth().weight(1f))
        }
    }
}

@Composable
private fun Legend(chart: DetailBlock.Chart) {
    Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
        for (s in chart.series) {
            if (s.label.isBlank()) continue
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(SwatchWidth, SwatchHeight).background(toneColor(s.tone), RoundedCornerShape(2.dp)))
                Spacer(Modifier.width(6.dp))
                Text(s.label, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1)
            }
        }
    }
}

/**
 * The plot, drawn with Paths built once per size (and per chart) in the draw cache, so a frame only replays them.
 * Labels are measured with the text engine and drawn with `drawText`, at the 16 sp `detail` size.
 */
@Composable
private fun Plot(chart: DetailBlock.Chart, modifier: Modifier) {
    val measurer = rememberTextMeasurer()
    val labelStyle = remember { HakuType.detail.copy(color = Haku.inkMuted) }
    Spacer(
        modifier.drawWithCache {
            val gap = AxisGap.toPx()
            val pad = EdgePad.toPx()

            // Size the gutters from the labels first: widest y label on the left, one text line under the plot.
            val yWidest = chart.y?.ticks.orEmpty().filter { it.label.isNotBlank() }
                .maxOfOrNull { measurer.measure(it.label, labelStyle, softWrap = false, maxLines = 1).size.width }
            val lineHeight = measurer.measure("0", labelStyle).size.height.toFloat()
            val insets = PlotInsets(
                left = if (yWidest != null) yWidest + gap else pad,
                top = if (yWidest != null) max(lineHeight / 2f, pad) else pad,
                right = pad,
                bottom = if (chart.xTicks.isNotEmpty()) lineHeight + gap else pad,
            )
            val g = chartGeometry(chart, size.width, size.height, insets)

            val lines = g.series.map { it.lines.toPath(close = false) }
            val fills = g.series.map { it.fills.toPath(close = true) }
            val tones = chart.series.map { toneColor(it.tone) }
            val brushes = g.series.mapIndexed { n, s ->
                // Strongest at the series' peak, so a low series is not washed out by a tall scale.
                val peak = s.lines.minOfOrNull { l -> (1 until l.size step 2).minOf { l[it] } } ?: g.top
                Brush.verticalGradient(
                    listOf(tones[n].copy(alpha = FILL_ALPHA), tones[n].copy(alpha = 0f)),
                    startY = peak, endY = max(g.baseline, peak + 1f),
                )
            }
            val stroke = Stroke(LineWidth.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
            val dot = DotRadius.toPx()
            val grid = GridWidth.toPx()

            val yLabels = g.yTicks.filter { it.label.isNotBlank() }.map {
                val l = measurer.measure(it.label, labelStyle, softWrap = false, maxLines = 1)
                Triple(l, g.left - gap - l.size.width, (it.pos - l.size.height / 2f).coerceIn(0f, size.height - l.size.height))
            }
            val strongStyle = labelStyle.copy(color = Haku.ink)
            val placed = g.xTicks.filter { it.label.isNotBlank() }.map {
                val l = measurer.measure(it.label, if (it.strong) strongStyle else labelStyle, softWrap = false, maxLines = 1)
                Triple(l, min(it.pos + pad, size.width - l.size.width), it.strong)
            }
            val shown = thinLabels(placed.map { (l, x, strong) -> LabelSpan(x, l.size.width.toFloat(), strong) }, gap)
            val xLabels = placed.filterIndexed { n, _ -> shown[n] }.map { (l, x, _) -> Pair(l, x) }

            onDrawBehind {
                for (t in g.yTicks) drawLine(Gridline, Offset(g.left, t.pos), Offset(g.right, t.pos), grid)
                for (t in g.xTicks) {
                    drawLine(if (t.strong) NowLine else DayLine, Offset(t.pos, g.top), Offset(t.pos, g.bottom),
                        if (t.strong) grid * NOW_LINE_SCALE else grid)
                }
                for (n in g.series.indices) {
                    drawPath(fills[n], brushes[n])
                    drawPath(lines[n], tones[n], style = stroke)
                    val d = g.series[n].dots
                    for (k in d.indices step 2) drawCircle(tones[n], dot, Offset(d[k], d[k + 1]))
                }
                for ((l, x, y) in yLabels) drawText(l, topLeft = Offset(x, y))
                for ((l, x) in xLabels) drawText(l, topLeft = Offset(x, g.bottom + gap))
            }
        },
    )
}

/** Each FloatArray (x,y pairs) as a subpath: open for a line, closed for a fill polygon. */
private fun List<FloatArray>.toPath(close: Boolean): Path = Path().also { path ->
    for (pts in this) {
        if (pts.size < 2) continue
        path.moveTo(pts[0], pts[1])
        for (k in 2 until pts.size step 2) path.lineTo(pts[k], pts[k + 1])
        if (close) path.close()
    }
}
