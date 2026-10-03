package io.haku.tablet

import io.haku.tablet.data.HubJson
import io.haku.tablet.data.HubState
import io.haku.tablet.ui.UiState
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.model.CardModel
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.model.HOLD_GRACE_MS
import io.haku.tablet.ui.model.PollTracker
import io.haku.tablet.ui.model.Pulse
import io.haku.tablet.ui.model.TileHold
import io.haku.tablet.ui.model.ValueModel
import io.haku.tablet.ui.model.project
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.ZoneId

class PollTrackerTest {
    private val demoDir = File("src/debug/assets/demo")
    private val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
    private fun demo(name: String): HubState = HubJson.parseState(File(demoDir, "$name.json").readText())

    /** Virtual wall clock: each [poll] lands 5 s after the last, like the view model's loop. */
    private var now = 0L
    private fun PollTracker.poll(name: String) = onOk(config, demo(name), now.also { now += 5_000 }).cards

    /** One water card, so the cooldown tests can flip `active` and `severity` exactly. */
    private val waterConfig = HubJson.parseConfig(
        """{"modules":[{"id":"water","kind":"water","title":"Water","tile":{"type":"value"}}]}""",
    )

    private fun water(active: Boolean, alert: Boolean = false): HubState = HubJson.parseState(
        """{"water":{"stale":false,"tile":{"hero":"0.4 L/min","sub":"","detail":"",""" +
            """"severity":"${if (alert) "high" else "normal"}","active":$active}}}""",
    )

    private fun PollTracker.water(atMs: Long, active: Boolean, alert: Boolean = false): ValueModel =
        onOk(waterConfig, water(active, alert), atMs).cards["water"] as ValueModel

    private val valueIds = setOf("doors", "laundry", "water", "energy", "climate", "weather", "gas")
    private val quietToBusy = setOf("climate", "doors", "gas", "laundry", "water")

    private fun base(c: CardModel?): ValueModel = when (c) {
        is ValueModel -> c
        is DoorsModel -> c.base
        is LaundryModel -> c.base
        else -> error("not a value-like card: $c")
    }

    private fun Map<String, CardModel>.agenda(id: String) = this[id] as AgendaModel

    /** Newest item time in a fixture's timeline, the value the next poll highlights after. */
    private fun newestActivity(name: String): Long =
        demo(name).items("timeline").mapNotNull { it.whenTs }.max()

    private fun withoutCounts(cards: Map<String, CardModel>): Map<String, CardModel> = cards.mapValues { (_, c) ->
        when (c) {
            is ValueModel -> c.copy(pulseCount = 0)
            is DoorsModel -> c.copy(base = c.base.copy(pulseCount = 0))
            is LaundryModel -> c.copy(base = c.base.copy(pulseCount = 0))
            is AgendaModel -> c
        }
    }

    @Test
    fun gap_rebaselines_without_pulse_or_highlight() {
        val t = PollTracker()
        t.poll("quiet")
        t.onFail()
        val busy = t.poll("busy")
        // Exactly a cold projection: no seq bumps, no pulse counts, no highlight baseline.
        assertEquals(project(config, demo("busy")), busy)
        for (id in valueIds) assertEquals("$id seq", 0, base(busy[id]).pulseSeq)
        assertNull(busy.agenda("timeline").highlightAfter)

        // The next good poll compares against busy, so busy -> alert still rings.
        val alert = t.poll("alert")
        assertEquals(1, base(alert["energy"]).pulseSeq)
        assertEquals(2, base(alert["energy"]).pulseCount)
        assertEquals(newestActivity("busy"), alert.agenda("timeline").highlightAfter)
    }

    @Test
    fun consecutive_ok_polls_pulse_what_changed() {
        val fired = mutableListOf<Map<String, Pulse>>()
        val t = PollTracker { fired += it }
        t.poll("quiet")
        val busy = t.poll("busy")
        for (id in valueIds) {
            val expect = if (id in quietToBusy) 1 else 0
            assertEquals("$id seq", expect, base(busy[id]).pulseSeq)
            assertEquals("$id count", expect, base(busy[id]).pulseCount)
        }

        // busy -> alert: doors and laundry ring a second time (as alerts), energy for the first.
        val alert = t.poll("alert")
        assertEquals(2, base(alert["doors"]).pulseSeq)
        assertEquals(2, base(alert["doors"]).pulseCount)
        assertEquals(2, base(alert["laundry"]).pulseSeq)
        assertEquals(1, base(alert["energy"]).pulseSeq)
        assertEquals(2, base(alert["energy"]).pulseCount)
        // Water stopped (falling edge) and gas went stale: seq kept, no ring.
        assertEquals(1, base(alert["water"]).pulseSeq)
        assertEquals(0, base(alert["water"]).pulseCount)
        assertEquals(1, base(alert["gas"]).pulseSeq)
        assertEquals(0, base(alert["gas"]).pulseCount)

        assertEquals(
            listOf(
                quietToBusy.associateWith { Pulse.ACTIVE },
                listOf("doors", "energy", "laundry").associateWith { Pulse.ALERT },
            ),
            fired,
        )
    }

    @Test
    fun steady_poll_clears_counts_and_keeps_seq() {
        val t = PollTracker()
        t.poll("quiet")
        val first = t.poll("busy")
        val second = t.poll("busy")
        for (id in valueIds) {
            assertEquals("$id seq", if (id in quietToBusy) 1 else 0, base(second[id]).pulseSeq)
            assertEquals("$id count", 0, base(second[id]).pulseCount)
        }
        // Value cards are unchanged apart from the counts. (Agenda highlightAfter moves on; see the handoff test.)
        assertEquals(withoutCounts(first).filterKeys { it in valueIds }, second.filterKeys { it in valueIds })
    }

    @Test
    fun identical_polls_give_equal_maps() {
        val t = PollTracker()
        val first = t.poll("quiet")
        val second = t.poll("quiet")
        val third = t.poll("quiet")
        // A quiet house re-emits an equal UiState, so the StateFlow conflates it and nothing recomposes.
        assertEquals(second, third)
        assertEquals(UiState("s", cards = second), UiState("s", cards = third))
        // Only the first poll after a cold start differs: it has no highlight baseline yet.
        assertEquals(first - "timeline", second - "timeline")
        assertNull(first.agenda("timeline").highlightAfter)
        assertEquals(newestActivity("quiet"), second.agenda("timeline").highlightAfter)
    }

    @Test
    fun highlight_after_hands_off_previous_newest() {
        val t = PollTracker()
        assertNull(t.poll("quiet").agenda("timeline").highlightAfter)    // cold start
        val busy1 = t.poll("busy")
        assertEquals(newestActivity("quiet"), busy1.agenda("timeline").highlightAfter)
        val busy2 = t.poll("busy")
        assertEquals(newestActivity("busy"), busy2.agenda("timeline").highlightAfter)
        // Calendar items carry no `when`, so there is nothing to hand off.
        assertNull(busy2.agenda("calendar").highlightAfter)
    }

    @Test
    fun flapping_active_pulses_once_per_cooldown() {
        var at = 0L
        val rang = mutableListOf<Long>()
        val t = PollTracker { if (it["water"] == Pulse.ACTIVE) rang += at }
        // The live meter at a trickle: 0.0 <-> 0.4 L/min, flipping every 15 s for 5 min.
        for (i in 0..20) {
            at = i * 15_000L
            val on = i % 2 == 1
            // The accent still follows every flip; only the ring is held back.
            assertEquals("active at $at ms", on, t.water(at, on).active)
        }
        // Only the first start rings: every later one comes within 120 s of the last stop.
        assertEquals(listOf(15_000L), rang)

        // It stopped at 300 s. Once it has stayed off for the whole cooldown, a start rings again.
        at = 420_000
        val back = t.water(at, active = true)
        assertEquals(1, back.pulseCount)
        assertEquals(2, back.pulseSeq)
        assertEquals(listOf(15_000L, 420_000L), rang)
    }

    @Test
    fun alert_pulse_never_suppressed() {
        val t = PollTracker()
        t.water(0, active = true)
        t.water(5_000, active = false)                               // stopped: cooling down
        assertEquals(0, t.water(10_000, active = true).pulseCount)   // so this start is held
        t.water(15_000, active = false)
        // Over its threshold 5 s after stopping: the alert rings, twice, anyway.
        val alert = t.water(20_000, active = true, alert = true)
        assertEquals(2, alert.pulseCount)
        assertEquals(1, alert.pulseSeq)
        // An alert on a card that isn't active (energy over its threshold) rings too.
        t.water(25_000, active = false)
        assertEquals(2, t.water(30_000, active = false, alert = true).pulseCount)
    }

    @Test
    fun cooldown_expires_after_120s() {
        // Stopped at 10 s and back on at 129.999 s: still cooling down, no ring, no seq bump.
        val held = PollTracker()
        held.water(0, active = true)
        held.water(10_000, active = false)
        val early = held.water(129_999, active = true)
        assertEquals(0, early.pulseCount)
        assertEquals(0, early.pulseSeq)

        // Back on at 130 s: the full 120 s has passed, so it rings.
        val rings = PollTracker()
        rings.water(0, active = true)
        rings.water(10_000, active = false)
        val onTime = rings.water(130_000, active = true)
        assertEquals(1, onTime.pulseCount)
        assertEquals(1, onTime.pulseSeq)

        // A wall clock stepped backwards can't hold a ring back for longer than the cooldown.
        val stepped = PollTracker()
        stepped.water(600_000, active = true)
        stepped.water(605_000, active = false)
        assertEquals(1, stepped.water(5_000, active = true).pulseCount)
    }

    /** The water meter out: the sidecar's placeholder hero, flagged stale. */
    private val waterOut: HubState = HubJson.parseState(
        """{"water":{"stale":true,"tile":{"hero":"-- L/min","severity":"normal","active":false}}}""",
    )

    @Test
    fun entering_and_leaving_a_hold_never_rings() {
        val rang = mutableListOf<Map<String, Pulse>>()
        // No grace, so the held card greys at once: this is about rings, not timing.
        val t = PollTracker(TileHold(ZoneId.of("UTC"), graceMs = 0)) { rang += it }
        t.water(0, active = false)
        val on = t.water(5_000, active = true)
        assertEquals(1, on.pulseSeq)
        assertEquals(1, on.pulseCount)

        // The meter drops out: the held card keeps its reading and seq, goes quiet, and rings nothing.
        val held = t.onOk(waterConfig, waterOut, 10_000).cards["water"] as ValueModel
        assertEquals("0.4 L/min", held.hero)
        assertTrue(held.stale)
        assertFalse(held.active)
        assertEquals(1, held.pulseSeq)
        assertEquals(0, held.pulseCount)
        assertEquals(held, t.onOk(waterConfig, waterOut, 15_000).cards["water"])

        // It comes back flowing and over its threshold, long after the cooldown: leaving a hold rings nothing.
        val back = t.water(400_000, active = true, alert = true)
        assertEquals(1, back.pulseSeq)
        assertEquals(0, back.pulseCount)
        assertEquals(listOf(mapOf("water" to Pulse.ACTIVE)), rang)

        // Live again, so its next rising edge rings as usual.
        t.water(405_000, active = false)
        val alert = t.water(410_000, active = false, alert = true)
        assertEquals(2, alert.pulseSeq)
        assertEquals(2, alert.pulseCount)
    }

    @Test
    fun degraded_names_stale_cards_held_or_not() {
        val t = PollTracker()
        assertEquals(emptyList<String>(), t.onOk(config, demo("quiet"), 0).degraded)
        t.onOk(config, demo("busy"), 5_000)
        // Gas goes stale in the alert fixture. Inside the hold's grace it is not degraded yet...
        assertEquals(emptyList<String>(), t.onOk(config, demo("alert"), 10_000).degraded)
        // ...past it, it is held at busy's reading, greyed, and counts as degraded.
        val alert = t.onOk(config, demo("alert"), 5_000 + HOLD_GRACE_MS)
        assertEquals(listOf("Gas"), alert.degraded)
        assertEquals("1.2 m³/h", base(alert.cards["gas"]).hero)
        // Recovered: nothing degraded.
        assertEquals(emptyList<String>(), t.onOk(config, demo("quiet"), 10_000 + HOLD_GRACE_MS).degraded)
    }

    @Test
    fun degraded_is_in_config_order_with_doors_and_laundry_but_never_agenda() {
        val cfg = HubJson.parseConfig(
            """{"modules":[
              {"id":"doors","kind":"doors","title":"Doors"},
              {"id":"water","kind":"water","title":"Water"},
              {"id":"calendar","kind":"calendar","title":"Calendar","tile":{"type":"agenda"}},
              {"id":"gas","kind":"gas","title":"Gas"},
              {"id":"laundry","kind":"laundry","title":"Laundry"},
              {"id":"x","kind":"weather"}
            ]}""",
        )
        val st = HubJson.parseState(
            """{
              "doors":{"stale":true,"doors":[],"tile":{"hero":"All closed"}},
              "water":{"stale":true,"tile":{"hero":"-- L/min"}},
              "calendar":{"stale":true,"items":[]},
              "gas":{"stale":false,"tile":{"hero":"0.8 m³/h"}},
              "laundry":{"stale":true,"machines":[],"tile":{"hero":"Laundry idle"}},
              "x":{"error":"timeout"}
            }""",
        )
        // A module with no title goes by its id.
        assertEquals(listOf("Doors", "Water", "Laundry", "x"), PollTracker().onOk(cfg, st, 0).degraded)
    }
}
