package io.haku.tablet

import io.haku.tablet.ui.backdrop.meanLuma
import io.haku.tablet.ui.backdrop.scrimAlpha
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ScrimTest {
    private val lumas = (0..100).map { it / 100f }

    @Test
    fun `monotonic_in_luma`() {
        for (top in listOf(true, false)) {
            lumas.zipWithNext().forEach { (a, b) ->
                assertTrue("top=$top $a..$b", scrimAlpha(b, top) >= scrimAlpha(a, top))
            }
        }
        assertTrue(scrimAlpha(1f, top = true) > scrimAlpha(0f, top = true))
    }

    @Test
    fun `top_at_least_bottom`() {
        for (l in lumas) assertTrue("luma $l", scrimAlpha(l, top = true) >= scrimAlpha(l, top = false))
    }

    @Test
    fun `within_bounds`() {
        for (l in lumas + listOf(-1f, 2f, Float.NaN)) {
            for (top in listOf(true, false)) {
                val a = scrimAlpha(l, top)
                assertTrue("luma $l top=$top gave $a", a in 0.25f..0.75f)
            }
        }
    }

    @Test
    fun `meanLuma_white_is_1_black_is_0`() {
        val w = 16
        val h = 10
        assertEquals(1f, meanLuma(IntArray(w * h) { 0xFFFFFFFF.toInt() }, w, topRows = 2), 1e-4f)
        assertEquals(0f, meanLuma(IntArray(w * h) { 0xFF000000.toInt() }, w, topRows = 2), 1e-4f)
        assertEquals(0f, meanLuma(IntArray(0), w, topRows = 2), 0f)
    }

    @Test
    fun `meanLuma_bright_header_band_dominates`() {
        // A white sky across the top 2 rows of an otherwise black frame: the clock sits on the sky.
        val w = 16
        val h = 10
        val px = IntArray(w * h) { i -> if (i < 2 * w) 0xFFFFFFFF.toInt() else 0xFF000000.toInt() }
        assertEquals(1f, meanLuma(px, w, topRows = 2), 1e-4f)
        // A bright frame with a dark band still reports the frame's brightness.
        val inverse = IntArray(w * h) { i -> if (i < 2 * w) 0xFF000000.toInt() else 0xFFFFFFFF.toInt() }
        assertEquals(0.8f, meanLuma(inverse, w, topRows = 2), 1e-4f)
        // A degenerate band never yields NaN.
        assertEquals(0.8f, meanLuma(inverse, w, topRows = 0), 1e-4f)
    }
}
