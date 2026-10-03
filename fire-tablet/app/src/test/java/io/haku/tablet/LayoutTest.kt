package io.haku.tablet

import io.haku.tablet.data.TileSpec
import io.haku.tablet.ui.Freshness
import io.haku.tablet.ui.GridArea
import io.haku.tablet.ui.LAGGING_AFTER_MS
import io.haku.tablet.ui.OFFLINE_AFTER_MS
import io.haku.tablet.ui.freshness
import io.haku.tablet.ui.freshnessFlow
import io.haku.tablet.ui.tileRect
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

class LayoutTest {
    // 4x3 grid on a 1024x600 screen: 12 side/bottom margins, a 56 header, 10 gap.
    // cellW = (1024 - 12 - 12 - 3*10) / 4 = 242.5; cellH = (600 - 56 - 12 - 2*10) / 3 = 170.67.
    private val area = GridArea(1024f, 600f, left = 12f, top = 56f, right = 12f, bottom = 12f, gap = 10f)
    private fun rect(tile: TileSpec) = tileRect(4, 3, tile, area)

    @Test
    fun `cell_0_0_at_insets`() {
        val r = rect(TileSpec(col = 0, row = 0))
        assertEquals(12f, r.x, 0.01f)
        assertEquals(56f, r.y, 0.01f)
        assertEquals(242.5f, r.w, 0.01f)
        assertEquals(170.67f, r.h, 0.01f)
    }

    @Test
    fun `activity_column_full_height`() {
        val r = rect(TileSpec(col = 3, row = 0, h = 3))
        assertEquals(12f + 3 * (242.5f + 10f), r.x, 0.01f)
        assertEquals(56f, r.y, 0.01f)
        assertEquals(532f, r.h, 0.01f)
        // The column's bottom edge lands on the bottom margin.
        assertEquals(600f - 12f, r.y + r.h, 0.01f)
    }

    @Test
    fun `double_width_span`() {
        val r = rect(TileSpec(col = 1, row = 1, w = 2))
        assertEquals(495f, r.w, 0.01f)
        assertEquals(12f + 242.5f + 10f, r.x, 0.01f)
        assertEquals(56f + 170.67f + 10f, r.y, 0.01f)
    }

    @Test
    fun `calendar_double_height`() {
        // The tablet layout's calendar: column 2, rows 0 and 1.
        val r = rect(TileSpec(col = 2, row = 0, h = 2))
        assertEquals(12f + 2 * (242.5f + 10f), r.x, 0.01f)
        assertEquals(56f, r.y, 0.01f)
        assertEquals(242.5f, r.w, 0.01f)
        assertEquals(2 * 170.67f + 10f, r.h, 0.01f)
    }

    @Test
    fun `span_clamped`() {
        val r = rect(TileSpec(col = 3, row = 2, w = 3, h = 2))
        assertEquals(242.5f, r.w, 0.01f)
        assertEquals(170.67f, r.h, 0.01f)
        // A tile placed past the grid snaps to the last cell.
        val past = rect(TileSpec(col = 9, row = 9))
        assertEquals(r.x, past.x, 0.01f)
        assertEquals(r.y, past.y, 0.01f)
    }

    @Test
    fun `freshness boundaries`() {
        val now = 1_000_000L
        assertEquals(Freshness.OFFLINE, freshness(null, now))
        assertEquals(Freshness.LIVE, freshness(now - 30_000, now))
        assertEquals(Freshness.LAGGING, freshness(now - 30_001, now))
        assertEquals(Freshness.LAGGING, freshness(now - 120_000, now))
        assertEquals(Freshness.OFFLINE, freshness(now - 120_001, now))
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test
    fun `freshness flow emits only at boundaries then stops at offline`() = runTest {
        val lastOk = MutableStateFlow<Long?>(0L)   // a poll landed at t = 0
        val seen = mutableListOf<Pair<Long, Freshness>>()
        backgroundScope.launch { freshnessFlow(lastOk, clock = { currentTime }).collect { seen += currentTime to it } }

        runCurrent()
        advanceTimeBy(LAGGING_AFTER_MS)   // age == 30 s is still live
        assertEquals(listOf(0L to Freshness.LIVE), seen)
        advanceTimeBy(1)
        runCurrent()
        assertEquals(30_001L to Freshness.LAGGING, seen.last())
        advanceTimeBy(OFFLINE_AFTER_MS - LAGGING_AFTER_MS)   // t = 120_001
        runCurrent()
        assertEquals(120_001L to Freshness.OFFLINE, seen.last())
        advanceTimeBy(10 * 60_000L)   // nothing more once offline
        assertEquals(3, seen.size)
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test
    fun `freshness flow stays quiet while polls keep arriving and recovers from offline`() = runTest {
        val lastOk = MutableStateFlow<Long?>(null)
        val seen = mutableListOf<Freshness>()
        backgroundScope.launch { freshnessFlow(lastOk, clock = { currentTime }).collect { seen += it } }

        runCurrent()
        assertEquals(listOf(Freshness.OFFLINE), seen)   // never fetched
        repeat(12) {   // a poll every 5 s for a minute
            lastOk.value = currentTime
            runCurrent()
            advanceTimeBy(5_000)
        }
        assertEquals(listOf(Freshness.OFFLINE, Freshness.LIVE), seen)
        advanceTimeBy(OFFLINE_AFTER_MS + 1_000)   // the polls stop
        runCurrent()
        assertEquals(listOf(Freshness.OFFLINE, Freshness.LIVE, Freshness.LAGGING, Freshness.OFFLINE), seen)
        lastOk.value = currentTime   // a poll lands again
        runCurrent()
        assertEquals(Freshness.LIVE, seen.last())
    }
}
