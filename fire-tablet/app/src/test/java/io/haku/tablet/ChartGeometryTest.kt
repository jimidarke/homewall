package io.haku.tablet

import io.haku.tablet.data.DetailBlock
import io.haku.tablet.data.Run
import io.haku.tablet.data.Series
import io.haku.tablet.data.XTick
import io.haku.tablet.data.YAxis
import io.haku.tablet.data.YTick
import io.haku.tablet.ui.detail.LabelSpan
import io.haku.tablet.ui.detail.PlotInsets
import io.haku.tablet.ui.detail.bucketX
import io.haku.tablet.ui.detail.chartGeometry
import io.haku.tablet.ui.detail.niceScale
import io.haku.tablet.ui.detail.thinLabels
import io.haku.tablet.ui.detail.valueY
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChartGeometryTest {
    // A 120 x 100 box with insets leaving a plot of x 20..120 and y 10..80: 10 buckets of 10 px, 70 px tall.
    private val insets = PlotInsets(left = 20f, top = 10f, right = 0f, bottom = 20f)
    private val axis = YAxis(0f, 60f, listOf(YTick(0f, "0"), YTick(30f, "30 L"), YTick(60f, "60 L")))

    private fun run(i: Int, vararg v: Float) = Run(i, v)

    private fun chart(
        vararg series: Series,
        count: Int = 10,
        y: YAxis? = axis,
        xTicks: List<XTick> = emptyList(),
    ) = DetailBlock.Chart(null, 0L, 3600L, count, series.toList(), xTicks, y, null)

    private fun s(vararg runs: Run, fill: Boolean = false) = Series("S", "water", fill, runs.toList())

    private fun geometry(c: DetailBlock.Chart) = chartGeometry(c, 120f, 100f, insets)

    // ---- bucket and value mapping ----

    @Test
    fun bucket_x_is_the_centre_of_its_slot() {
        assertEquals(25f, bucketX(0, 10, 20f, 120f), 1e-4f)
        assertEquals(75f, bucketX(5, 10, 20f, 120f), 1e-4f)
        assertEquals(115f, bucketX(9, 10, 20f, 120f), 1e-4f)
        assertEquals(70f, bucketX(0, 1, 20f, 120f), 1e-4f)   // a single bucket is the middle
        // 168 hourly buckets over 840 px: 5 px each, point 0 at 2.5.
        assertEquals(2.5f, bucketX(0, 168, 0f, 840f), 1e-4f)
        assertEquals(837.5f, bucketX(167, 168, 0f, 840f), 1e-4f)
    }

    @Test
    fun value_y_maps_the_scale_bottom_to_top() {
        assertEquals(80f, valueY(0f, 0f, 60f, 10f, 80f), 1e-4f)
        assertEquals(10f, valueY(60f, 0f, 60f, 10f, 80f), 1e-4f)
        assertEquals(45f, valueY(30f, 0f, 60f, 10f, 80f), 1e-4f)
        assertEquals(40f, valueY(0f, -10f, 10f, 20f, 60f), 1e-4f)   // a scale through zero: its middle
        assertEquals(20f, valueY(10f, -10f, 10f, 20f, 60f), 1e-4f)
    }

    @Test
    fun values_clamp_into_the_scale() {
        assertEquals(80f, valueY(-5f, 0f, 60f, 10f, 80f), 1e-4f)
        assertEquals(10f, valueY(1000f, 0f, 60f, 10f, 80f), 1e-4f)
        assertEquals(80f, valueY(Float.NEGATIVE_INFINITY, 0f, 60f, 10f, 80f), 1e-4f)
        assertEquals(80f, valueY(5f, 3f, 3f, 10f, 80f), 1e-4f)   // a degenerate scale cannot divide by zero
    }

    @Test
    fun the_plot_rectangle_follows_the_insets() {
        val g = geometry(chart())
        assertEquals(listOf(20f, 10f, 120f, 80f), listOf(g.left, g.top, g.right, g.bottom))
        assertEquals(listOf(0f, 60f), listOf(g.min, g.max))
    }

    @Test
    fun insets_larger_than_the_box_leave_an_empty_plot_not_a_negative_one() {
        val g = chartGeometry(chart(s(run(0, 1f, 2f))), 30f, 20f, PlotInsets(50f, 30f, 50f, 30f))
        assertTrue(g.right >= g.left && g.bottom >= g.top)
    }

    // ---- polylines, dots, fills ----

    @Test
    fun a_run_is_a_polyline_of_xy_pairs() {
        val g = geometry(chart(s(run(2, 0f, 30f, 60f))))
        assertEquals(1, g.series[0].lines.size)
        assertArrayEquals(floatArrayOf(45f, 80f, 55f, 45f, 65f, 10f), g.series[0].lines[0], 1e-4f)
        assertEquals(0, g.series[0].dots.size)
        assertTrue(g.series[0].fills.isEmpty())
    }

    @Test
    fun runs_are_separate_polylines_so_a_gap_is_never_bridged() {
        val g = geometry(chart(s(run(0, 10f, 20f, 30f), run(5, 40f, 50f))))
        val lines = g.series[0].lines
        assertEquals(2, lines.size)
        assertEquals(6, lines[0].size)
        assertEquals(4, lines[1].size)
        assertEquals(45f, lines[0][4], 1e-4f)        // the first run ends at bucket 2
        assertEquals(75f, lines[1][0], 1e-4f)        // the second starts at bucket 5, with nothing between
    }

    @Test
    fun a_single_bucket_run_is_a_dot_not_a_line() {
        val g = geometry(chart(s(run(0, 30f, 30f), run(4, 30f), run(9, 60f))))
        assertEquals(1, g.series[0].lines.size)
        assertArrayEquals(floatArrayOf(65f, 45f, 115f, 10f), g.series[0].dots, 1e-4f)
    }

    @Test
    fun values_are_clamped_in_the_lines_too() {
        val g = geometry(chart(s(run(0, -50f, 500f))))
        assertArrayEquals(floatArrayOf(25f, 80f, 35f, 10f), g.series[0].lines[0], 1e-4f)
    }

    @Test
    fun a_fill_polygon_closes_down_to_the_baseline() {
        val g = geometry(chart(s(run(1, 30f, 60f), run(6, 0f, 30f, 60f), run(9, 5f), fill = true)))
        val fills = g.series[0].fills
        assertEquals("one polygon per line, none for the dot", 2, fills.size)
        // The first: its two points, then straight down from the last and back along the baseline to the first.
        assertArrayEquals(
            floatArrayOf(35f, 45f, 45f, 10f, 45f, 80f, 35f, 80f), fills[0], 1e-4f,
        )
        assertEquals(g.baseline, 80f, 1e-4f)
        assertEquals(3 * 2 + 4, fills[1].size)
        assertEquals(80f, fills[1][fills[1].size - 1], 1e-4f)
    }

    @Test
    fun the_baseline_is_the_zero_line_inside_the_plot() {
        val below = chart(s(run(0, -10f, 10f), fill = true), y = YAxis(-20f, 20f, emptyList()))
        assertEquals(45f, geometry(below).baseline, 1e-4f)
        val above = chart(s(run(0, 5f, 8f), fill = true), y = YAxis(2f, 10f, emptyList()))
        assertEquals("zero is below the scale: the bottom edge", 80f, geometry(above).baseline, 1e-4f)
        val under = chart(s(run(0, -5f, -8f), fill = true), y = YAxis(-10f, -2f, emptyList()))
        assertEquals("zero is above the scale: the top edge", 10f, geometry(under).baseline, 1e-4f)
    }

    @Test
    fun series_keep_their_order_and_stay_independent() {
        val g = geometry(chart(s(run(0, 10f, 20f)), s(run(3, 30f), run(5, 40f, 50f)), s()))
        assertEquals(3, g.series.size)
        assertEquals(1, g.series[0].lines.size)
        assertEquals(1, g.series[1].lines.size)
        assertEquals(2, g.series[1].dots.size)
        assertTrue(g.series[2].lines.isEmpty() && g.series[2].dots.isEmpty())
    }

    // ---- ticks ----

    @Test
    fun y_ticks_sit_at_their_values_with_their_labels() {
        val g = geometry(chart())
        assertEquals(listOf("0", "30 L", "60 L"), g.yTicks.map { it.label })
        assertEquals(listOf(80f, 45f, 10f), g.yTicks.map { it.pos })
    }

    @Test
    fun y_ticks_outside_the_scale_are_dropped() {
        val y = YAxis(0f, 60f, listOf(YTick(-10f, "-10"), YTick(0f, "0"), YTick(60f, "60"), YTick(90f, "90")))
        assertEquals(listOf("0", "60"), geometry(chart(y = y)).yTicks.map { it.label })
    }

    @Test
    fun x_ticks_sit_under_their_buckets() {
        val ticks = listOf(XTick(0, "Fri"), XTick(4, "Sat"), XTick(10, "past the end"), XTick(-1, "before"))
        val g = geometry(chart(xTicks = ticks))
        assertEquals(listOf("Fri", "Sat"), g.xTicks.map { it.label })
        assertEquals(listOf(25f, 65f), g.xTicks.map { it.pos })
    }

    // ---- a scale derived from the data ----

    @Test
    fun without_a_y_the_scale_comes_from_the_data_and_has_no_labels() {
        val g = geometry(chart(s(run(0, 3f, 47f, 20f)), y = null))
        assertTrue(g.min <= 3f && g.max >= 47f)
        assertTrue("a few gridlines", g.yTicks.size >= 2)
        assertTrue("and no labels", g.yTicks.all { it.label.isEmpty() })
    }

    @Test
    fun a_filling_series_without_a_y_starts_at_zero() {
        val g = geometry(chart(s(run(0, 30f, 47f), fill = true), y = null))
        assertEquals(0f, g.min, 0f)
        assertEquals(60f, g.max, 0f)
        assertEquals(listOf(0f, 20f, 40f, 60f).map { valueY(it, 0f, 60f, 10f, 80f) }, g.yTicks.map { it.pos })
        assertEquals(80f, g.baseline, 1e-4f)
    }

    @Test
    fun a_line_without_a_y_keeps_a_tight_range() {
        val g = geometry(chart(s(run(0, 21f, 22f)), y = null))
        assertEquals(21f, g.min, 0f)
        assertEquals(22f, g.max, 0f)
    }

    // ---- degenerate charts ----

    @Test
    fun an_empty_chart_has_a_scale_and_no_marks() {
        val g = geometry(chart(s(), y = null))
        assertEquals(0f, g.min, 0f)
        assertEquals(1f, g.max, 0f)
        assertTrue(g.series.single().lines.isEmpty())
        assertTrue(chartGeometry(chart(count = 0), 120f, 100f, insets).series.isEmpty())
    }

    @Test
    fun a_chart_with_no_buckets_does_not_divide_by_zero() {
        val g = chartGeometry(chart(s(run(0, 1f, 2f)), count = 0, xTicks = listOf(XTick(0, "a"))), 120f, 100f, insets)
        assertTrue(g.xTicks.isEmpty())
        assertTrue(g.series[0].lines[0].all { it.isFinite() })
    }

    // ---- niceScale ----

    @Test
    fun nice_scale_picks_round_steps() {
        assertEquals(Triple(0f, 60f, 20f), niceScale(0f, 47f).let { Triple(it.min, it.max, it.step) })
        assertEquals(Triple(0f, 1.5f, 0.5f), niceScale(0f, 1.4f).let { Triple(it.min, it.max, it.step) })
        assertEquals(Triple(-5f, 15f, 5f), niceScale(-5f, 15f).let { Triple(it.min, it.max, it.step) })
        assertEquals(Triple(0f, 60f, 20f), niceScale(0f, 60f).let { Triple(it.min, it.max, it.step) })
        assertEquals(Triple(0f, 100f, 50f), niceScale(3f, 99f, intervals = 2).let { Triple(it.min, it.max, it.step) })
        assertEquals(Triple(0f, 2500f, 500f), niceScale(0f, 2300f, intervals = 5).let { Triple(it.min, it.max, it.step) })
    }

    @Test
    fun nice_scale_always_covers_the_data() {
        val rnd = java.util.Random(7)
        repeat(500) {
            val a = (rnd.nextFloat() - 0.5f) * 2000f
            val b = a + rnd.nextFloat() * 1000f
            val n = niceScale(a, b)
            assertTrue("$a..$b -> ${n.min}..${n.max}", n.min <= a + 1e-3f && n.max >= b - 1e-3f)
            assertTrue(n.max > n.min && n.step > 0f)
            val ticks = n.ticks()
            assertEquals(n.min, ticks.first(), 1e-3f)
            assertEquals(n.max, ticks.last(), 1e-3f * n.max.coerceAtLeast(1f))
            assertTrue("a handful of gridlines, not dozens: ${ticks.size}", ticks.size in 2..11)
        }
    }

    @Test
    fun a_flat_range_is_widened() {
        val zero = niceScale(0f, 0f)
        assertEquals(0f, zero.min, 0f)
        assertEquals(1f, zero.max, 0f)
        val flat = niceScale(21f, 21f)
        assertTrue(flat.min < 21f && flat.max > 21f)
        val inverted = niceScale(47f, 0f)
        assertEquals(niceScale(0f, 47f), inverted)
    }

    @Test
    fun nice_scale_ticks_run_min_to_max_by_step() {
        assertEquals(listOf(0f, 20f, 40f, 60f), niceScale(0f, 47f).ticks())
        assertEquals(listOf(-5f, 0f, 5f, 10f, 15f), niceScale(-5f, 15f).ticks())
        assertEquals(listOf(0f, 0.25f, 0.5f, 0.75f, 1f), niceScale(0f, 1f).ticks())
    }

    // ---- the strong "Now" tick and x label priority ----

    @Test
    fun a_strong_tick_stays_strong_through_the_geometry() {
        val c = chart(s(run(0, 1f, 2f)), xTicks = listOf(XTick(2, "Thu"), XTick(5, "Now", strong = true)))
        assertEquals(listOf(false, true), geometry(c).xTicks.map { it.strong })
    }

    @Test
    fun the_middle_bucket_of_49_sits_at_the_centre_of_the_plot() {
        // Now is bucket 24 of 49: observed and forecast meet exactly in the middle.
        assertEquals(60f, bucketX(24, 49, 20f, 100f), 1e-3f)
    }

    @Test
    fun thinning_keeps_left_to_right_order_when_nothing_is_strong() {
        val spans = listOf(LabelSpan(0f, 40f, false), LabelSpan(30f, 40f, false), LabelSpan(60f, 40f, false))
        assertEquals(listOf(true, false, true), thinLabels(spans, gap = 8f))
    }

    @Test
    fun labels_exactly_a_gap_apart_both_stay() {
        val spans = listOf(LabelSpan(0f, 40f, false), LabelSpan(48f, 40f, false))
        assertEquals(listOf(true, true), thinLabels(spans, gap = 8f))
    }

    @Test
    fun a_strong_label_wins_over_the_ones_it_overlaps() {
        // "6 PM" at 0..40 and "Now" at 30..70 (strong): left to right alone would drop Now.
        val spans = listOf(LabelSpan(0f, 40f, false), LabelSpan(30f, 40f, true), LabelSpan(80f, 40f, false))
        assertEquals(listOf(false, true, true), thinLabels(spans, gap = 8f))
    }

    @Test
    fun two_overlapping_strong_labels_keep_the_left_one() {
        val spans = listOf(LabelSpan(0f, 40f, true), LabelSpan(30f, 40f, true))
        assertEquals(listOf(true, false), thinLabels(spans, gap = 8f))
    }

    @Test
    fun no_labels_is_no_flags() {
        assertEquals(emptyList<Boolean>(), thinLabels(emptyList(), gap = 8f))
    }
}
