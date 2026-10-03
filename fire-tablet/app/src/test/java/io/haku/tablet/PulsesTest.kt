package io.haku.tablet

import io.haku.tablet.data.HubJson
import io.haku.tablet.data.HubState
import io.haku.tablet.ui.model.Pulse
import io.haku.tablet.ui.model.Signal
import io.haku.tablet.ui.model.project
import io.haku.tablet.ui.model.pulses
import io.haku.tablet.ui.model.signals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

class PulsesTest {
    private val quiet = Signal(active = false, alert = false, stale = false)
    private val active = Signal(active = true, alert = false, stale = false)
    private val alert = Signal(active = true, alert = true, stale = false)
    private val none = emptyMap<String, Pulse>()

    private val demoDir = File("src/debug/assets/demo")
    private val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
    private fun demo(name: String): HubState = HubJson.parseState(File(demoDir, "$name.json").readText())
    private fun demoSignals(name: String) = signals(project(config, demo(name)))

    @Test
    fun cold_start_no_pulses() {
        // First good poll lands on a busy, alerting house: it is the baseline, nothing rings.
        assertEquals(none, pulses(null, demoSignals("alert")))
        assertEquals(none, pulses(null, mapOf("a" to alert, "b" to active)))
    }

    @Test
    fun gap_rebaselines() {
        // Poll 1 ok and quiet; poll 2 fails (prev = null); poll 3 ok and active.
        val poll3 = mapOf("a" to active, "b" to alert)
        assertEquals(none, pulses(null, poll3))
        // Poll 4 compares only against poll 3, so the change that happened during the gap never rings.
        assertEquals(none, pulses(poll3, mapOf("a" to active, "b" to alert)))
    }

    @Test
    fun stale_to_fresh_no_pulse() {
        // An HA or sidecar restart: everything goes stale, then comes back fresh and busy. No storm.
        val before = mapOf("a" to quiet, "b" to quiet, "c" to quiet)
        val restarting = before.mapValues { (_, s) -> s.copy(stale = true) }
        val back = mapOf("a" to active, "b" to alert, "c" to quiet)
        assertEquals(none, pulses(before, restarting))
        assertEquals(none, pulses(restarting, back))
        // Fresh to stale never rings either, even if the stale value reads active.
        assertEquals(none, pulses(before, mapOf("a" to alert.copy(stale = true))))
    }

    @Test
    fun new_id_no_pulse() {
        // A config reload added "b": it has no previous signal, so it cannot have changed.
        assertEquals(none, pulses(mapOf("a" to quiet), mapOf("a" to quiet, "b" to alert)))
    }

    @Test
    fun inactive_to_active_pulses_active() {
        assertEquals(
            mapOf("a" to Pulse.ACTIVE),
            pulses(mapOf("a" to quiet, "b" to quiet), mapOf("a" to active, "b" to quiet)),
        )
        // Demo quiet -> busy: everything that started running rings once.
        assertEquals(
            listOf("climate", "doors", "gas", "laundry", "water").associateWith { Pulse.ACTIVE },
            pulses(demoSignals("quiet"), demoSignals("busy")),
        )
    }

    @Test
    fun normal_to_alert_pulses_alert_even_if_also_activating() {
        assertEquals(mapOf("a" to Pulse.ALERT), pulses(mapOf("a" to quiet), mapOf("a" to alert)))
        assertEquals(mapOf("a" to Pulse.ALERT), pulses(mapOf("a" to active), mapOf("a" to alert)))
        // Demo busy -> alert: doors and laundry were already active, energy was not; gas went stale.
        assertEquals(
            listOf("doors", "energy", "laundry").associateWith { Pulse.ALERT },
            pulses(demoSignals("busy"), demoSignals("alert")),
        )
    }

    @Test
    fun active_to_active_no_pulse() {
        val busy = mapOf("a" to active, "b" to alert)
        assertEquals(none, pulses(busy, busy))
        // Falling edges never ring.
        assertEquals(none, pulses(busy, mapOf("a" to quiet, "b" to quiet)))
        assertEquals(none, pulses(demoSignals("alert"), demoSignals("quiet")))
    }

    @Test
    fun signals_exclude_agenda() {
        val sig = demoSignals("busy")
        assertEquals(setOf("doors", "laundry", "water", "energy", "climate", "weather", "gas"), sig.keys)
        // Doors and laundry signal from their summary tile.
        assertEquals(active, sig["doors"])
        assertEquals(active, sig["laundry"])
        assertEquals(quiet, sig["weather"])
        assertEquals(Signal(active = false, alert = false, stale = true), demoSignals("alert")["gas"])
    }
}
