package io.haku.tablet

import io.haku.tablet.ui.cards.ledAnimates
import io.haku.tablet.ui.cards.ledColorFor
import io.haku.tablet.ui.cards.ledFrame
import io.haku.tablet.ui.cards.ledStepMs
import io.haku.tablet.ui.theme.Haku
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LaundryFramesTest {
    private val eps = 1e-6f

    private fun frame(mode: String, t: Long, leds: Int = 0, stale: Boolean = false) = ledFrame(mode, leds, t, stale)

    /** The one segment lit at full brightness, with every other segment dark. */
    private fun soleLit(f: FloatArray): Int {
        val lit = f.indices.filter { f[it] == 1f }
        assertEquals("exactly one lit segment in ${f.toList()}", 1, lit.size)
        f.indices.filter { it != lit[0] }.forEach { assertEquals(0f, f[it], eps) }
        return lit[0]
    }

    @Test
    fun idle_frame() {
        assertArrayEquals(floatArrayOf(0.25f, 0f, 0f, 0f), frame("idle", t = 0), eps)
        assertArrayEquals(floatArrayOf(0.25f, 0f, 0f, 0f), frame("idle", t = 12_345), eps)
    }

    @Test
    fun running_leds_clamped() {
        assertArrayEquals(floatArrayOf(1f, 1f, 1f, 0f), frame("running", t = 0, leds = 3), eps)
        assertArrayEquals(floatArrayOf(1f, 1f, 1f, 1f), frame("running", t = 0, leds = 9), eps)
        assertArrayEquals(floatArrayOf(0f, 0f, 0f, 0f), frame("running", t = 0, leds = -1), eps)
        // Static: time does not move it.
        assertArrayEquals(frame("running", t = 0, leds = 2), frame("running", t = 9_999, leds = 2), eps)
    }

    @Test
    fun overtime_breathes_within_bounds() {
        var lo = 1f
        var hi = 0f
        for (t in 0L..2_500L step 10) {
            val f = frame("overtime", t)
            assertTrue("segment 0 at t=$t is ${f[0]}", f[0] in 0.15f - eps..1f + eps)
            assertArrayEquals(floatArrayOf(0f, 0f, 0f), f.copyOfRange(1, 4), eps)
            lo = minOf(lo, f[0])
            hi = maxOf(hi, f[0])
        }
        // It really breathes over the 2.5 s cycle: full at the crest (t = 625), 0.15 in the trough (t = 1875).
        assertEquals(1f, hi, 1e-4f)
        assertEquals(0.15f, lo, 1e-4f)
    }

    @Test
    fun done_pingpong_positions() {
        val ts = longArrayOf(0, 120, 360, 480, 600, 720)
        val expected = listOf(0, 1, 3, 2, 1, 0)
        assertEquals(expected, ts.map { soleLit(frame("done", it)) })
    }

    @Test
    fun done_calm_head_and_trail() {
        assertArrayEquals(floatArrayOf(0.2f, 0.6f, 0f, 0f), frame("done_calm", t = 450), eps)
        // Step 0 has no previous step, so no trail.
        assertArrayEquals(floatArrayOf(0.6f, 0f, 0f, 0f), frame("done_calm", t = 0), eps)
        // Turning at the far end: head back on 2, trail on 3.
        assertArrayEquals(floatArrayOf(0f, 0f, 0.6f, 0.2f), frame("done_calm", t = 4 * 450L), eps)
        // A new cycle (step 6) keeps its trail: the head returns to 0 from 1.
        assertArrayEquals(floatArrayOf(0.6f, 0.2f, 0f, 0f), frame("done_calm", t = 6 * 450L), eps)
    }

    @Test
    fun stale_comet_wraps() {
        assertArrayEquals(floatArrayOf(1f, 0f, 0.1f, 0.35f), frame("idle", t = 0, stale = true), eps)
        assertArrayEquals(floatArrayOf(0.35f, 1f, 0f, 0.1f), frame("idle", t = 150, stale = true), eps)
        assertArrayEquals(floatArrayOf(0f, 0.1f, 0.35f, 1f), frame("idle", t = 450, stale = true), eps)
        assertArrayEquals(frame("idle", t = 0, stale = true), frame("idle", t = 600, stale = true), eps)
        // Stale overrides every mode.
        for (mode in listOf("running", "overtime", "done", "done_calm", "bogus")) {
            val expected = frame("idle", t = 150, stale = true)
            assertArrayEquals(mode, expected, frame(mode, t = 150, leds = 3, stale = true), eps)
        }
    }

    @Test
    fun unknown_mode_is_dark() {
        assertArrayEquals(floatArrayOf(0f, 0f, 0f, 0f), frame("spinning", t = 0, leds = 4), eps)
        assertArrayEquals(floatArrayOf(0f, 0f, 0f, 0f), frame("", t = 500), eps)
    }

    @Test
    fun step_ms_table() {
        assertNull(ledStepMs("idle"))
        assertNull(ledStepMs("running"))
        assertEquals(100L, ledStepMs("overtime"))
        assertEquals(120L, ledStepMs("done"))
        assertEquals(450L, ledStepMs("done_calm"))
        assertEquals(150L, ledStepMs("stale"))
        assertNull(ledStepMs("spinning"))
        // Every animated mode steps at 10 fps or slower.
        listOf("overtime", "done", "done_calm", "stale").forEach { assertTrue(it, ledStepMs(it)!! >= 100L) }
    }

    @Test
    fun led_color_rules() {
        val washer = Haku.washer
        assertEquals(Haku.ledIdleRed, ledColorFor("idle", stale = false, machineColor = washer))
        for (mode in listOf("running", "overtime", "done", "done_calm")) {
            assertEquals(mode, washer, ledColorFor(mode, stale = false, machineColor = washer))
        }
        for (mode in listOf("idle", "running", "done")) {
            assertEquals(mode, Haku.ledStaleViolet, ledColorFor(mode, stale = true, machineColor = washer))
        }
    }

    @Test
    fun quiet_card_holds_its_leds_still() {
        for (mode in listOf("overtime", "done", "done_calm")) {
            // An animated mode steps while the card is live...
            assertTrue(mode, ledAnimates(mode, machineStale = false, quiet = false))
            // ...and holds its first frame while the app is offline or the whole card is stale.
            assertFalse(mode, ledAnimates(mode, machineStale = false, quiet = true))
        }
        for (mode in listOf("idle", "running", "unknown-mode")) {
            assertFalse(mode, ledAnimates(mode, machineStale = false, quiet = false))
            assertFalse(mode, ledAnimates(mode, machineStale = false, quiet = true))
        }
        // A machine HA has no data for sweeps its comet on a live card, whatever its mode ("no data" means
        // something), but not when the whole card is quiet.
        assertTrue(ledAnimates("idle", machineStale = true, quiet = false))
        assertTrue(ledAnimates("running", machineStale = true, quiet = false))
        assertFalse(ledAnimates("done", machineStale = true, quiet = true))
    }
}
