package io.haku.tablet

import io.haku.tablet.ui.Freshness
import io.haku.tablet.ui.HeaderStatus
import io.haku.tablet.ui.bannerText
import io.haku.tablet.ui.headerStatus
import io.haku.tablet.ui.offlineShown
import io.haku.tablet.ui.theme.Haku
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.TimeZone

class OfflineTest {
    @Test
    fun offline_waits_for_the_first_state_fetch() {
        // Cold start: freshness is OFFLINE until a poll lands, but nothing has been fetched yet.
        assertFalse(offlineShown(Freshness.OFFLINE, stateFetched = false))
        assertTrue(offlineShown(Freshness.OFFLINE, stateFetched = true))
        assertFalse(offlineShown(Freshness.LAGGING, stateFetched = true))
        assertFalse(offlineShown(Freshness.LIVE, stateFetched = true))
    }

    @Test
    fun banner_reads_since_and_error() {
        val saved = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"))
            val t = 1_790_000_000_000L - 1_790_000_000_000L % 86_400_000L + (21 * 60 + 41) * 60_000L   // 21:41 UTC
            assertEquals("No data since 9:41 PM · network: timeout", bannerText(t, "network: timeout"))
            assertEquals("No data since 9:41 PM", bannerText(t, null))
            assertEquals("No data yet · http 502", bannerText(null, "http 502"))
            assertEquals("No data yet", bannerText(null, null))
        } finally {
            TimeZone.setDefault(saved)
        }
    }

    @Test
    fun header_says_connecting_until_the_first_state_fetch() {
        fun status(fresh: Freshness, fetched: Boolean) = headerStatus(fresh, fetched, degraded = emptyList())
        // Cold start: freshness reads OFFLINE before any poll, but nothing has been tried yet.
        assertEquals(HeaderStatus("connecting", Haku.offline), status(Freshness.OFFLINE, fetched = false))
        assertEquals(HeaderStatus("connecting", Haku.offline), status(Freshness.LIVE, fetched = false))
        // Once a fetch has finished, success or not, the dot tells the truth.
        assertEquals(HeaderStatus("offline", Haku.offline), status(Freshness.OFFLINE, fetched = true))
        assertEquals(HeaderStatus("lagging", Haku.amber), status(Freshness.LAGGING, fetched = true))
        assertEquals(HeaderStatus("live", Haku.sage), status(Freshness.LIVE, fetched = true))
    }

    @Test
    fun header_says_degraded_below_connecting_offline_and_lagging() {
        val water = listOf("Water")
        // Priority: connecting > offline > lagging > degraded > live. Old data outranks a stale module.
        assertEquals(HeaderStatus("connecting", Haku.offline), headerStatus(Freshness.LIVE, false, water))
        assertEquals(HeaderStatus("offline", Haku.offline), headerStatus(Freshness.OFFLINE, true, water))
        assertEquals(HeaderStatus("lagging", Haku.amber), headerStatus(Freshness.LAGGING, true, water))
        assertEquals(HeaderStatus("degraded · Water", Haku.amber), headerStatus(Freshness.LIVE, true, water))
        assertEquals(HeaderStatus("live", Haku.sage), headerStatus(Freshness.LIVE, true, emptyList()))
    }

    @Test
    fun degraded_names_up_to_two_then_counts() {
        fun label(vararg titles: String) = headerStatus(Freshness.LIVE, true, titles.toList()).label
        assertEquals("degraded · Water", label("Water"))
        assertEquals("degraded · Water, Gas", label("Water", "Gas"))
        assertEquals("degraded · 3", label("Water", "Gas", "Weather"))
        assertEquals("degraded · 7", label("a", "b", "c", "d", "e", "f", "g"))
    }
}
