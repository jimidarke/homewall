package io.haku.tablet

import io.haku.tablet.ui.burnInOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class BurnInTest {
    private val slot = 10 * 60_000L

    /** A real wall-clock time (2026-10-01), so the slot arithmetic is checked away from zero too. */
    private val base = 1_790_000_000_000L - 1_790_000_000_000L % slot

    @Test
    fun offsets_within_2dp() {
        for (t in (0 until 40).map { base + it * slot + 1_234L } + listOf(0L, slot - 1, 7 * slot)) {
            val o = burnInOffset(t)
            assertTrue("$t -> $o", abs(o.x) <= 2 && abs(o.y) <= 2)
        }
    }

    @Test
    fun changes_every_10_minutes() {
        for (k in 0 until 16) {
            val start = base + k * slot
            assertEquals("same slot $k", burnInOffset(start), burnInOffset(start + slot - 1))
            assertEquals("same slot $k", burnInOffset(start), burnInOffset(start + 4 * 60_000L))
            assertNotEquals("next slot after $k", burnInOffset(start), burnInOffset(start + slot))
        }
    }

    @Test
    fun cycles_through_8_positions() {
        val round = (0 until 8).map { burnInOffset(base + it * slot) }
        assertEquals("8 distinct positions", 8, round.toSet().size)
        assertEquals("then repeats", round, (8 until 16).map { burnInOffset(base + it * slot) })
        // A ring, stepped in order: each move is one 2 dp step on one axis, never a jump across.
        for (i in round.indices) {
            val a = round[i]
            val b = round[(i + 1) % round.size]
            assertEquals("step $i: $a -> $b", 2, abs(a.x - b.x) + abs(a.y - b.y))
        }
    }
}
