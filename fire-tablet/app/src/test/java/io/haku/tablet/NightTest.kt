package io.haku.tablet

import io.haku.tablet.ui.clampBrightness
import io.haku.tablet.ui.isNight
import io.haku.tablet.ui.minuteOfDay
import io.haku.tablet.ui.minuteTicks
import io.haku.tablet.ui.parseHm
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NightTest {
    private fun min(h: Int, m: Int) = h * 60 + m
    private fun night(minute: Int, start: String = "22:00", end: String = "06:30") = isNight(minute, start, end)

    @Test
    fun `inside_wrapped_window`() = assertTrue(night(min(23, 30)))

    @Test
    fun `early_morning_inside`() = assertTrue(night(min(5, 0)))

    @Test
    fun `after_end`() = assertFalse(night(min(6, 30)))   // end is exclusive

    @Test
    fun `at_start_inclusive`() = assertTrue(night(min(22, 0)))

    @Test
    fun `daytime_false`() = assertFalse(night(min(12, 0)))

    @Test
    fun `non_wrapping_window`() {
        assertTrue(night(min(13, 0), "13:00", "14:00"))
        assertTrue(night(min(13, 59), "13:00", "14:00"))
        assertFalse(night(min(14, 0), "13:00", "14:00"))
        assertFalse(night(min(12, 59), "13:00", "14:00"))
        assertFalse(night(min(23, 0), "13:00", "14:00"))
    }

    @Test
    fun `blank_or_invalid_false`() {
        assertFalse(night(min(23, 30), "", ""))
        assertFalse(night(min(23, 30), "22:00", ""))
        assertFalse(night(min(23, 30), "", "06:30"))
        assertFalse(night(min(23, 30), "late", "early"))
        assertFalse(night(min(23, 30), "25:00", "06:30"))
    }

    @Test
    fun `equal_start_end_false`() {
        assertFalse(night(min(22, 0), "22:00", "22:00"))
        assertFalse(night(min(3, 0), "22:00", "22:00"))
    }

    @Test
    fun `parseHm parses and rejects`() {
        assertEquals(1320, parseHm("22:00"))
        assertEquals(425, parseHm("7:05"))
        assertEquals(0, parseHm("0:00"))
        assertEquals(1439, parseHm("23:59"))
        assertNull(parseHm("24:00"))
        assertNull(parseHm("12:60"))
        assertNull(parseHm(""))
        assertNull(parseHm("noon"))
        assertNull(parseHm("12"))
        assertNull(parseHm("1:2:3"))
    }

    @Test
    fun `brightness is clamped to 0_01 and 1`() {
        assertEquals(0.01f, clampBrightness(0f), 0f)
        assertEquals(0.01f, clampBrightness(-3f), 0f)
        assertEquals(0.15f, clampBrightness(0.15f), 0f)
        assertEquals(1f, clampBrightness(7f), 0f)
    }

    @Test
    fun `minuteOfDay is local wall clock time in the zone`() {
        val edmonton = ZoneId.of("America/Edmonton")
        // 2026-10-01T05:30:00Z is 23:30 the evening before in Edmonton (MDT, UTC-6).
        assertEquals(min(23, 30), minuteOfDay(1_790_832_600_000L, edmonton))
        assertEquals(min(5, 30), minuteOfDay(1_790_832_600_000L, ZoneId.of("UTC")))
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test
    fun `minuteTicks emits now then once per minute boundary`() = runTest {
        val start = 120_000L + 45_000L   // 45 s into a minute
        val ticks = mutableListOf<Long>()
        backgroundScope.launch { minuteTicks { start + currentTime }.collect { ticks += it } }

        runCurrent()
        assertEquals(listOf(start), ticks)
        advanceTimeBy(14_999)
        assertEquals(1, ticks.size)
        advanceTimeBy(1)
        runCurrent()
        assertEquals(listOf(start, 180_000L), ticks)
        advanceTimeBy(60_000)
        runCurrent()
        assertEquals(240_000L, ticks.last())
        assertEquals(3, ticks.size)
    }
}
