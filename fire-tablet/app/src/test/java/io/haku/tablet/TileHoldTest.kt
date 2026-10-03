package io.haku.tablet

import io.haku.tablet.data.AgendaItem
import io.haku.tablet.data.Door
import io.haku.tablet.data.HubJson
import io.haku.tablet.data.Machine
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.model.CardModel
import io.haku.tablet.ui.model.HOLD_GRACE_MS
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.model.PollTracker
import io.haku.tablet.ui.model.TileHold
import io.haku.tablet.ui.model.ValueModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.Locale
import java.util.TimeZone

class TileHoldTest {
    /** The house's zone, pinned so "as of" and midnight don't depend on the machine running the tests. */
    private val zone = ZoneId.of("America/Edmonton")

    /** Wall time of [h]:[m] on October [day], 2026, in the house's zone. */
    private fun at(day: Int, h: Int, m: Int): Long =
        ZonedDateTime.of(2026, 10, day, h, m, 0, 0, zone).toInstant().toEpochMilli()

    private fun water(
        hero: String,
        stale: Boolean = false,
        active: Boolean = false,
        alert: Boolean = false,
        seq: Int = 0,
        count: Int = 0,
    ) = ValueModel(
        id = "water", kind = "water", title = "Water", glyph = if (active) "water" else "water-outline",
        hero = hero, sub = "412 L today", detail = "$1.24 today",
        alert = alert, active = active, level = if (stale) null else 40, stale = stale,
        pulseSeq = seq, pulseCount = count,
    )

    private val out = water("-- L/min", stale = true)

    private fun TileHold.poll(vararg cards: CardModel, atMs: Long): Map<String, CardModel> =
        apply(cards.associateBy { it.id }, atMs)

    @Test
    fun stale_value_card_shows_its_last_good_reading_greyed() {
        val hold = TileHold(zone)
        val good = water("4.2 L/min", active = true, alert = true, seq = 2, count = 1)
        assertSame("a fresh card passes through", good, hold.poll(good, atMs = at(1, 19, 41))["water"])

        val held = hold.poll(out.copy(pulseSeq = 3), atMs = at(1, 19, 50))["water"]
        assertEquals(
            good.copy(
                stale = true, active = false, alert = false,
                pulseSeq = 3, pulseCount = 0, asOf = "as of 7:41 PM",
            ),
            held,
        )
        // Every poll while it's out gives an equal card, so the UI state conflates and nothing recomposes.
        assertEquals(held, hold.poll(out.copy(pulseSeq = 3), atMs = at(1, 20, 30))["water"])
    }

    @Test
    fun as_of_is_the_last_good_poll() {
        val hold = TileHold(zone)
        hold.poll(water("4.2 L/min"), atMs = at(1, 19, 41))
        hold.poll(water("3.9 L/min"), atMs = at(1, 19, 46))
        val held = hold.poll(out, atMs = at(1, 19, 52))["water"] as ValueModel
        assertEquals("3.9 L/min", held.hero)
        assertEquals("as of 7:46 PM", held.asOf)
    }

    @Test
    fun recovery_replaces_the_held_reading() {
        val hold = TileHold(zone)
        hold.poll(water("4.2 L/min"), atMs = at(1, 19, 41))
        hold.poll(out, atMs = at(1, 19, 50))
        val back = water("0 L/min")
        val shown = hold.poll(back, atMs = at(1, 20, 0))["water"] as ValueModel
        assertSame(back, shown)
        assertNull(shown.asOf)
        // The next outage holds the recovered reading, not the old one.
        val held = hold.poll(out, atMs = at(1, 20, 5))["water"] as ValueModel
        assertEquals("0 L/min", held.hero)
        assertEquals("as of 8:00 PM", held.asOf)
    }

    @Test
    fun held_reading_is_dropped_at_local_midnight() {
        val hold = TileHold(zone)
        hold.poll(water("4.2 L/min"), atMs = at(1, 23, 50))
        assertEquals("as of 11:50 PM", (hold.poll(out, atMs = at(1, 23, 59))["water"] as ValueModel).asOf)
        // Midnight in the house's zone: yesterday's reading is gone, and the stale card shows as sent.
        assertSame(out, hold.poll(out, atMs = at(2, 0, 0))["water"])
        assertSame("dropped, not just hidden", out, hold.poll(out, atMs = at(2, 0, 5))["water"])
        // A new good reading today is held again.
        hold.poll(water("1.0 L/min"), atMs = at(2, 6, 0))
        assertEquals("as of 6:00 AM", (hold.poll(out, atMs = at(2, 6, 5))["water"] as ValueModel).asOf)
    }

    @Test
    fun midnight_is_the_house_zone_not_utc() {
        // 7:00 PM in Edmonton (UTC-6 in October) is already the next day in UTC; here it's the day of 9:00 AM.
        val hold = TileHold(zone)
        hold.poll(water("4.2 L/min"), atMs = at(1, 9, 0))
        assertEquals("as of 9:00 AM", (hold.poll(out, atMs = at(1, 19, 0))["water"] as ValueModel).asOf)
    }

    @Test
    fun doors_laundry_and_agenda_are_never_held() {
        val hold = TileHold(zone)
        val door = Door("front", "Front", "closed", "3h", "normal", "door-closed")
        val machine = Machine("washer", "Washer", "#00AAFF", "idle", 0, "idle", "washing-machine", false)
        fun base(id: String, kind: String, hero: String, stale: Boolean) = ValueModel(
            id = id, kind = kind, title = id, glyph = "", hero = hero, sub = "", detail = "",
            alert = false, active = false, level = null, stale = stale,
        )
        fun agenda(stale: Boolean) = AgendaModel(
            "calendar", "calendar", "Calendar", "calendar",
            listOf(AgendaItem("event", "Dentist", "", "3:30 PM", "normal")), activity = false,
            stale = stale, highlightAfter = null,
        )
        hold.poll(
            DoorsModel(base("doors", "doors", "All closed", false), listOf(door)),
            LaundryModel(base("laundry", "laundry", "Laundry idle", false), listOf(machine)),
            agenda(stale = false),
            base("garage", "doors", "Closed", false),   // a doors module that fell back to a value tile
            atMs = at(1, 12, 0),
        )
        val staleDoors = DoorsModel(base("doors", "doors", "—", true), emptyList())
        val staleLaundry = LaundryModel(base("laundry", "laundry", "—", true), listOf(machine.copy(stale = true)))
        val staleAgenda = agenda(stale = true)
        val staleGarage = base("garage", "doors", "—", true)
        val next = hold.poll(staleDoors, staleLaundry, staleAgenda, staleGarage, atMs = at(1, 12, 5))
        assertSame(staleDoors, next["doors"])
        assertSame(staleLaundry, next["laundry"])
        assertSame(staleAgenda, next["calendar"])
        assertSame(staleGarage, next["garage"])
    }

    @Test
    fun a_config_reload_forgets_removed_modules() {
        val hold = TileHold(zone)
        val gas = water("0.8 m³/h").copy(id = "gas", kind = "gas", title = "Gas")
        hold.poll(water("4.2 L/min"), gas, atMs = at(1, 12, 0))
        hold.poll(gas, atMs = at(1, 12, 5))   // water left the config
        // Water came back in a later reload: it has nothing held, so its stale card shows as sent.
        val staleGas = gas.copy(stale = true, hero = "-- m³/h")
        val next = hold.poll(out, staleGas, atMs = at(1, 12, 10))
        assertSame(out, next["water"])
        assertEquals("as of 12:05 PM", (next["gas"] as ValueModel).asOf)
    }

    @Test
    fun the_hold_survives_a_failed_poll() {
        val config = HubJson.parseConfig("""{"modules":[{"id":"water","kind":"water","title":"Water"}]}""")
        val good = HubJson.parseState("""{"water":{"stale":false,"tile":{"hero":"4.2 L/min","detail":"$1.24"}}}""")
        val down = HubJson.parseState("""{"water":{"stale":true,"tile":{"hero":"-- L/min"}}}""")
        val tracker = PollTracker(TileHold(zone))
        tracker.onOk(config, good, at(1, 19, 41))
        tracker.onFail()
        val held = tracker.onOk(config, down, at(1, 19, 51)).cards["water"] as ValueModel
        assertEquals("4.2 L/min", held.hero)
        assertEquals("as of 7:41 PM", held.asOf)
    }

    @Test
    fun as_of_reads_like_the_banner_whatever_the_device_locale_and_zone() {
        val savedLocale = Locale.getDefault()
        val savedZone = TimeZone.getDefault()
        try {
            Locale.setDefault(Locale.CANADA)                       // whose own "a" would be "p.m."
            TimeZone.setDefault(TimeZone.getTimeZone("Asia/Tokyo"))  // the hold's zone wins
            val hold = TileHold(zone)
            hold.poll(water("4.2 L/min"), atMs = at(1, 7, 5))
            assertEquals("as of 7:05 AM", (hold.poll(out, atMs = at(1, 7, 10))["water"] as ValueModel).asOf)
            hold.poll(water("4.2 L/min"), atMs = at(1, 12, 0))
            assertEquals("as of 12:00 PM", (hold.poll(out, atMs = at(1, 12, 6))["water"] as ValueModel).asOf)
        } finally {
            Locale.setDefault(savedLocale)
            TimeZone.setDefault(savedZone)
        }
    }

    @Test
    fun a_short_dropout_shows_the_last_reading_as_live() {
        val hold = TileHold(zone)
        val good = water("4.2 L/min", active = true, seq = 2, count = 1)
        hold.poll(good, atMs = at(1, 19, 41))
        // Out a minute later: the card shows its last reading untouched (not greyed, no "as of"), keeps the
        // live pulseSeq and rings nothing.
        val blip = hold.poll(out.copy(pulseSeq = 2), atMs = at(1, 19, 42))["water"] as ValueModel
        assertEquals(good.copy(pulseCount = 0), blip)
        // Still out just inside the grace, then just past it: now greyed, as of the last good reading.
        assertEquals(blip, hold.poll(out.copy(pulseSeq = 2), atMs = at(1, 19, 41) + HOLD_GRACE_MS - 1)["water"])
        val greyed = hold.poll(out.copy(pulseSeq = 2), atMs = at(1, 19, 41) + HOLD_GRACE_MS)["water"] as ValueModel
        assertEquals(true, greyed.stale)
        assertEquals("as of 7:41 PM", greyed.asOf)
    }

    @Test
    fun a_source_that_blips_and_recovers_never_greys() {
        val hold = TileHold(zone)
        var t = at(1, 21, 0)
        // Up two minutes, down a minute and a half, over and over (the water meter on 2026-10-01).
        repeat(5) {
            assertEquals(false, (hold.poll(water("0 L/min"), atMs = t)["water"] as ValueModel).stale)
            t += 120_000
            assertEquals(false, (hold.poll(out, atMs = t)["water"] as ValueModel).stale)
            t += 90_000
        }
    }
}
