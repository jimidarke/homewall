package io.haku.tablet

import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubJson
import io.haku.tablet.data.HubState
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.model.Pulse
import io.haku.tablet.ui.model.ValueModel
import io.haku.tablet.ui.model.project
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ProjectTest {
    private val demoDir = File("src/debug/assets/demo")
    private val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
    private fun demo(name: String): HubState = HubJson.parseState(File(demoDir, "$name.json").readText())
    private fun fixture(name: String) = javaClass.classLoader!!.getResource(name)!!.readText()
    private fun modules(vararg json: String): HubConfig =
        HubJson.parseConfig("""{"modules":[${json.joinToString(",")}]}""")

    @Test
    fun unknown_type_projects_to_value() {
        val cfg = modules(
            """{"id":"w","kind":"weather","title":"Weather","feedKey":"weather","tile":{"type":"sparkline"}}""",
        )
        val card = project(cfg, demo("busy"))["w"]
        assertTrue("got $card", card is ValueModel)
        card as ValueModel
        assertEquals("7°", card.hero)
        assertEquals("weather-rainy", card.glyph)
    }

    @Test
    fun doors_kind_with_array_projects_doors() {
        val card = project(config, demo("busy"))["doors"]
        assertTrue("got $card", card is DoorsModel)
        card as DoorsModel
        assertEquals("doors", card.id)
        assertEquals(listOf("front", "back"), card.doors.map { it.id })
        assertEquals("Doors", card.base.title)
        assertEquals("Back open", card.base.hero)
        assertTrue(card.base.active)
    }

    @Test
    fun doors_kind_without_array_falls_back_to_value() {
        val cfg = modules("""{"id":"doors","kind":"doors","title":"Doors"}""")
        val st = HubJson.parseState("""{"doors":{"open_count":0,"tile":{"hero":"All closed","severity":"normal"}}}""")
        val card = project(cfg, st)["doors"]
        assertTrue("got $card", card is ValueModel)
        assertEquals("All closed", (card as ValueModel).hero)
    }

    @Test
    fun laundry_kind_projects_laundry_or_falls_back_to_value() {
        val card = project(config, demo("busy"))["laundry"]
        assertTrue("got $card", card is LaundryModel)
        card as LaundryModel
        assertEquals("laundry", card.id)
        assertEquals(listOf("washer", "dryer"), card.machines.map { it.id })
        assertEquals("Washer 34m left", card.base.hero)

        val noArray = HubJson.parseState("""{"laundry":{"tile":{"hero":"Laundry idle"}}}""")
        assertTrue(project(config, noArray)["laundry"] is ValueModel)
    }

    @Test
    fun live_fixtures_project_doors_and_laundry_models() {
        val cards = project(
            HubJson.parseConfig(fixture("config.json")),
            HubJson.parseState(fixture("state.json")),
        )
        assertEquals(9, cards.size)

        val doors = cards["doors"]
        assertTrue("got $doors", doors is DoorsModel)
        assertEquals(listOf("front", "back"), (doors as DoorsModel).doors.map { it.id })
        assertEquals("All closed", doors.base.hero)

        val laundry = cards["laundry"]
        assertTrue("got $laundry", laundry is LaundryModel)
        assertEquals(listOf("washer", "dryer"), (laundry as LaundryModel).machines.map { it.id })
        assertEquals("Laundry idle", laundry.base.hero)
    }

    @Test
    fun agenda_projects_with_activity_flag() {
        val cards = project(config, demo("busy"), highlightAfter = mapOf("timeline" to 1790822340L))

        val activity = cards["timeline"] as AgendaModel
        assertTrue(activity.activity)
        assertEquals(8, activity.items.size)
        assertTrue(activity.items.none { it.kind == "header" })
        assertEquals("Activity", activity.title)
        assertEquals("history", activity.glyph)
        assertEquals(1790822340L, activity.highlightAfter)

        val calendar = cards["calendar"] as AgendaModel
        assertFalse(calendar.activity)
        assertEquals(8, calendar.items.size)
        assertTrue(calendar.items.any { it.kind == "header" })
        assertNull(calendar.highlightAfter)
    }

    @Test
    fun blank_hero_gives_dash_and_is_stale() {
        val cfg = modules("""{"id":"x","kind":"climate","title":"Thermostat"}""")
        for (hero in listOf("", "   ")) {
            val st = HubJson.parseState(
                """{"x":{"stale":false,"tile":{"hero":"$hero","sub":"Idle","severity":"normal"}}}""",
            )
            val card = project(cfg, st)["x"] as ValueModel
            assertEquals("hero '$hero'", "—", card.hero)
            assertEquals("Idle", card.sub)
            assertTrue("a blank hero is no reading, whatever the sidecar's flag says", card.stale)
        }
    }

    @Test
    fun missing_tile_gives_stale_dash_hero() {
        val cfg = modules("""{"id":"x","kind":"climate","title":"Thermostat"}""")
        val card = project(cfg, HubJson.parseState("{}"))["x"]
        assertEquals(
            ValueModel(
                id = "x", kind = "climate", title = "Thermostat", glyph = "",
                hero = "—", sub = "", detail = "",
                alert = false, active = false, level = null, stale = true,
            ),
            card,
        )
    }

    @Test
    fun module_error_is_stale_even_with_a_tile() {
        val cfg = modules("""{"id":"x","kind":"water","title":"Water"}""")
        val failed = HubJson.parseState("""{"x":{"error":"KeyError: 'flow'"}}""")
        assertTrue((project(cfg, failed)["x"] as ValueModel).stale)
        val both = HubJson.parseState("""{"x":{"error":"timeout","stale":false,"tile":{"hero":"4.2 L/min"}}}""")
        val card = project(cfg, both)["x"] as ValueModel
        assertEquals("4.2 L/min", card.hero)
        assertTrue(card.stale)
        // A good tile with no error is fresh.
        val ok = HubJson.parseState("""{"x":{"stale":false,"tile":{"hero":"4.2 L/min"}}}""")
        assertFalse((project(cfg, ok)["x"] as ValueModel).stale)
    }

    @Test
    fun value_fields_come_from_tile_and_state() {
        val cards = project(config, demo("alert"))
        val energy = cards["energy"] as ValueModel
        assertEquals("Energy", energy.title)
        assertEquals("energy", energy.kind)
        assertEquals("6.2 kW", energy.hero)
        assertEquals("flash", energy.glyph)
        assertTrue("severity high is an alert", energy.alert)
        assertFalse(energy.active)
        assertEquals(100, energy.level)
        assertFalse(energy.stale)

        val gas = cards["gas"] as ValueModel
        assertTrue(gas.stale)
        assertFalse("severity normal is not an alert", gas.alert)
        assertNull(gas.level)
    }

    @Test
    fun pulse_count_from_kind() {
        val cards = project(
            config, demo("alert"),
            pulseSeq = mapOf("doors" to 4, "water" to 2, "energy" to 7),
            pulseKind = mapOf("doors" to Pulse.ALERT, "water" to Pulse.ACTIVE),
        )
        val doors = (cards["doors"] as DoorsModel).base
        assertEquals(4, doors.pulseSeq)
        assertEquals(2, doors.pulseCount)
        val water = cards["water"] as ValueModel
        assertEquals(2, water.pulseSeq)
        assertEquals(1, water.pulseCount)
        // An earlier pulse leaves its seq behind; no pulse this poll means count 0.
        val energy = cards["energy"] as ValueModel
        assertEquals(7, energy.pulseSeq)
        assertEquals(0, energy.pulseCount)
        val weather = cards["weather"] as ValueModel
        assertEquals(0, weather.pulseSeq)
        assertEquals(0, weather.pulseCount)
    }
}
