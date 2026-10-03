package io.haku.tablet

import io.haku.tablet.data.Grid
import io.haku.tablet.data.HubJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ModelsTest {
    private fun fixture(name: String) =
        javaClass.classLoader!!.getResource(name)!!.readText()

    @Test
    fun `live config parses with unknown keys tolerated`() {
        val cfg = HubJson.parseConfig(fixture("config.json"))
        assertEquals(Grid(4, 3), cfg.grid)
        assertEquals(9, cfg.modules.size)
        val timeline = cfg.modules.first { it.id == "timeline" }
        assertEquals("agenda", timeline.tile.type)
        assertTrue(timeline.tile.dropHeaders)
        assertEquals("timeline", timeline.key)
        assertEquals(
            listOf("doors", "laundry", "timeline", "water", "energy", "climate", "weather", "gas", "calendar"),
            cfg.modules.map { it.id },
        )
        // `enabled` defaults to false, so true proves the live block was read. intervalMs records the live
        // value; it equals the default, so config_parses_background_and_nightdim covers its parsing.
        assertTrue(cfg.background.enabled)
        assertEquals(180_000L, cfg.background.intervalMs)
        assertEquals("22:00", cfg.nightDim!!.start)
    }

    @Test
    fun `feedKey falls back to id`() {
        val cfg = HubJson.parseConfig("""{"modules":[{"id":"x","kind":"weather","tile":{"type":"value"}}]}""")
        assertEquals("x", cfg.modules.single().key)
    }

    @Test
    fun `module without tile gets a default value tile`() {
        val cfg = HubJson.parseConfig("""{"modules":[{"id":"x","kind":"doors"}]}""")
        assertEquals("value", cfg.modules.single().tile.type)
    }

    @Test
    fun `state exposes tile values per feed key`() {
        val st = HubJson.parseState(fixture("state.json"))
        val energy = st.tile("energy")!!
        assertTrue(energy.hero.endsWith("kW"))
        assertEquals("normal", energy.severity)
        assertTrue(st.ts!! > 1_700_000_000L)
    }

    @Test
    fun unknown_key_has_no_tile() {
        val st = HubJson.parseState(fixture("state.json"))
        assertNull(st.tile("cameras"))      // the tablet layout has no cameras module
        assertNull(st.tile("nope"))
    }

    @Test
    fun `agenda items decode and headers can be dropped`() {
        val st = HubJson.parseState(fixture("state.json"))
        val all = st.items("timeline")
        assertTrue(all.any { it.kind == "header" })
        val events = st.items("timeline", dropHeaders = true)
        assertTrue(events.isNotEmpty())
        assertTrue(events.all { it.kind == "event" })
        assertTrue(events.first().title.isNotBlank())
    }

    @Test
    fun `tile with partial fields fills blanks`() {
        val st = HubJson.parseState("""{"gas":{"tile":{"hero":"0.0"}}}""")
        val t = st.tile("gas")!!
        assertEquals("0.0", t.hero)
        assertEquals("", t.sub)
        assertEquals("normal", t.severity)
    }

    // ---- UI v2: glyph / active / level, stale, doors, laundry, agenda extras, config blocks ----

    @Test
    fun live_value_tiles_all_carry_a_glyph() {
        val cfg = HubJson.parseConfig(fixture("config.json"))
        val st = HubJson.parseState(fixture("state.json"))
        val valueModules = cfg.modules.filter { it.tile.type == "value" }
        assertEquals(7, valueModules.size)
        for (m in valueModules) {
            assertTrue("${m.id} tile has a glyph", st.tile(m.key)!!.glyph.isNotEmpty())
        }
    }

    @Test
    fun live_gas_tile_is_active_while_burning() {
        val gas = HubJson.parseState(fixture("state.json")).tile("gas")!!
        assertEquals("fire", gas.glyph)
        assertTrue(gas.active)
    }

    @Test
    fun live_idle_tiles_are_not_active() {
        val st = HubJson.parseState(fixture("state.json"))
        val water = st.tile("water")!!
        assertEquals("water-outline", water.glyph)
        assertFalse(water.active)
        // Fan-only reads "Fan" but is not active (only heating or cooling is).
        val climate = st.tile("climate")!!
        assertEquals("fan", climate.glyph)
        assertEquals("Fan", climate.sub)
        assertFalse(climate.active)
    }

    @Test
    fun live_state_carries_doors_and_laundry_arrays() {
        val st = HubJson.parseState(fixture("state.json"))
        assertEquals(2, st.doors("doors")!!.size)
        assertEquals(2, st.laundry("laundry")!!.size)
    }

    @Test
    fun tile_reads_glyph_active_level() {
        val st = HubJson.parseState("""{"water":{"tile":{"hero":"57 L","glyph":"water","active":true,"level":55}}}""")
        val t = st.tile("water")!!
        assertEquals("water", t.glyph)
        assertTrue(t.active)
        assertEquals(55, t.level)
    }

    @Test
    fun tile_defaults_when_new_keys_absent() {
        val st = HubJson.parseState("""{"water":{"tile":{"hero":"57 L"}}}""")
        val t = st.tile("water")!!
        assertEquals("", t.glyph)
        assertFalse(t.active)
        assertNull(t.level)
    }

    @Test
    fun level_clamped_and_nonint_ignored() {
        val st = HubJson.parseState(
            """{"a":{"tile":{"level":140}},"b":{"tile":{"level":"x"}},"c":{"tile":{"level":-5}},"d":{"tile":{"level":null}}}""",
        )
        assertEquals(100, st.tile("a")!!.level)
        assertNull(st.tile("b")!!.level)
        assertEquals(0, st.tile("c")!!.level)
        assertNull(st.tile("d")!!.level)
    }

    @Test
    fun active_is_true_only_for_a_json_boolean_true() {
        val st = HubJson.parseState(
            """{"a":{"tile":{"active":"true"}},"b":{"tile":{"active":1}},"c":{"tile":{"active":false}}}""",
        )
        assertFalse(st.tile("a")!!.active)
        assertFalse(st.tile("b")!!.active)
        assertFalse(st.tile("c")!!.active)
    }

    @Test
    fun stale_reads_bool() {
        val st = HubJson.parseState("""{"gas":{"stale":true},"water":{"stale":false}}""")
        assertTrue(st.stale("gas"))
        assertFalse(st.stale("water"))
        assertFalse(st.stale("missing"))
    }

    @Test
    fun error_reads_the_module_error_string() {
        val st = HubJson.parseState(
            """{"water":{"error":"KeyError: 'flow'"},"gas":{"error":3},"climate":{"tile":{"hero":"21°"}}}""",
        )
        assertEquals("KeyError: 'flow'", st.error("water"))
        assertNull("only a string is an error", st.error("gas"))
        assertNull(st.error("climate"))
        assertNull(st.error("missing"))
    }

    @Test
    fun doors_parses_and_normalizes_state() {
        val st = HubJson.parseState(
            """{"doors":{"doors":[
                {"id":"front","label":"Front","state":"unavailable","age":"12m","severity":"","glyph":"door"},
                {"id":"back","label":"Back","state":"open","age":"6m","severity":"high","glyph":"door-open"}
            ]}}""",
        )
        val doors = st.doors("doors")!!
        assertEquals(2, doors.size)
        assertEquals("unknown", doors[0].state)
        assertEquals("front", doors[0].id)
        assertEquals("Front", doors[0].label)
        assertEquals("12m", doors[0].age)
        assertEquals("door", doors[0].glyph)
        assertEquals("normal", doors[0].severity)
        assertEquals("open", doors[1].state)
        assertEquals("high", doors[1].severity)
        assertEquals("door-open", doors[1].glyph)
    }

    @Test
    fun doors_null_when_absent() {
        val st = HubJson.parseState("""{"x":{"count":1},"y":{"doors":"nope"}}""")
        assertNull(st.doors("doors"))
        assertNull(st.doors("x"))
        assertNull(st.doors("y"))
    }

    @Test
    fun laundry_parses_machines_and_clamps_leds() {
        val st = HubJson.parseState(
            """{"laundry":{"machines":[
                {"id":"washer","label":"Washer","color":"#00AAFF","mode":"running","leds":9,
                 "status":"34m left","glyph":"washing-machine","stale":false},
                {"id":"dryer","label":"Dryer","color":"#FF6900","mode":"idle","leds":-2,
                 "status":"no data","glyph":"tumble-dryer","stale":true}
            ]}}""",
        )
        val m = st.laundry("laundry")!!
        assertEquals(2, m.size)
        assertEquals("washer", m[0].id)
        assertEquals("Washer", m[0].label)
        assertEquals("#00AAFF", m[0].color)
        assertEquals("running", m[0].mode)
        assertEquals(4, m[0].leds)
        assertEquals("34m left", m[0].status)
        assertEquals("washing-machine", m[0].glyph)
        assertFalse(m[0].stale)
        assertEquals(0, m[1].leds)
        assertEquals("no data", m[1].status)
        assertEquals("tumble-dryer", m[1].glyph)
        assertTrue(m[1].stale)
    }

    @Test
    fun laundry_null_when_absent() {
        val st = HubJson.parseState("""{"x":{"stale":false},"y":{"machines":{}}}""")
        assertNull(st.laundry("laundry"))
        assertNull(st.laundry("x"))
        assertNull(st.laundry("y"))
    }

    @Test
    fun items_read_glyph_dot_when() {
        val st = HubJson.parseState(
            """{"timeline":{"items":[
                {"kind":"event","title":"Back door","sub":"opened","time":"9:41","severity":"normal",
                 "glyph":"door-open","dot":"0xFF6900FF","when":1790822410},
                {"kind":"event","title":"Plain","time":"9:00"}
            ]}}""",
        )
        val items = st.items("timeline")
        assertEquals("door-open", items[0].glyph)
        assertEquals("0xFF6900FF", items[0].dot)
        assertEquals(1790822410L, items[0].whenTs)
        assertEquals("", items[1].glyph)
        assertEquals("", items[1].dot)
        assertNull(items[1].whenTs)
    }

    @Test
    fun config_parses_background_and_nightdim() {
        val cfg = HubJson.parseConfig(
            """{"grid":{"cols":4,"rows":3},
                "nightDim":{"start":"22:00","end":"06:30","brightness":0.15},
                "background":{"enabled":true,"intervalMs":120000},
                "modules":[]}""",
        )
        assertEquals(Grid(4, 3), cfg.grid)
        assertTrue(cfg.background.enabled)
        assertEquals(120_000L, cfg.background.intervalMs)
        val nd = cfg.nightDim!!
        assertEquals("22:00", nd.start)
        assertEquals("06:30", nd.end)
        assertEquals(0.15f, nd.brightness, 0.0001f)
    }

    @Test
    fun config_defaults_when_blocks_absent() {
        val cfg = HubJson.parseConfig("""{"modules":[]}""")
        assertFalse(cfg.background.enabled)
        assertEquals(180_000L, cfg.background.intervalMs)
        assertNull(cfg.nightDim)
        assertEquals(Grid(4, 3), cfg.grid)
        assertEquals(Grid(4, 3), Grid())
    }

    @Test
    fun demo_busy_fixture_reads_new_fields() {
        val st = HubJson.parseState(File("src/debug/assets/demo/busy.json").readText())
        val water = st.tile("water")!!
        assertEquals("water", water.glyph)
        assertTrue(water.active)
        val doors = st.doors("doors")!!
        assertEquals(2, doors.size)
        assertTrue(doors.any { it.state == "open" })
        val washer = st.laundry("laundry")!!.first { it.id == "washer" }
        assertEquals("34m left", washer.status)
        assertEquals(3, washer.leds)
    }
}
