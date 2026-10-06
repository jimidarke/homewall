package io.haku.tablet

import io.haku.tablet.ui.glyph.GLYPH_PATHS
import io.haku.tablet.ui.glyph.Glyphs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class GlyphsTest {
    /** Contract section 2.1 (37), plus the photo peek's two chevrons (0.4.0, DESIGN §8.10). */
    private val contractGlyphs = listOf(
        "door-open", "door-closed", "door",
        "washing-machine", "tumble-dryer",
        "water", "water-outline", "flash", "fire", "meter-gas",
        "snowflake", "fan", "thermostat",
        "calendar", "history",
        "motion-sensor", "motion-sensor-off", "lock", "lock-open-variant", "home-account", "account-arrow-right",
        "alert-circle-outline", "weather-sunny", "weather-night", "weather-partly-cloudy",
        "weather-night-partly-cloudy", "weather-cloudy", "weather-fog", "weather-hail", "weather-lightning",
        "weather-lightning-rainy", "weather-pouring", "weather-rainy", "weather-snowy", "weather-snowy-rainy",
        "weather-windy", "weather-windy-variant",
        "chevron-left", "chevron-right",
    )

    @Test
    fun all_contract_glyphs_present() {
        assertEquals(39, contractGlyphs.size)
        assertEquals(39, contractGlyphs.toSet().size)
        for (name in contractGlyphs) {
            val d = GLYPH_PATHS[name]
            assertTrue("no path data for '$name'", !d.isNullOrBlank())
            assertTrue("path data for '$name' should start with a moveto", d!!.startsWith("M", ignoreCase = true))
        }
        // The shipped subset is exactly the contract set; nothing extra rides along.
        assertEquals(contractGlyphs.toSet(), GLYPH_PATHS.keys)
    }

    @Test
    fun every_glyph_builds_a_vector() {
        for (name in contractGlyphs) {
            val v = Glyphs.vector(name)
            assertNotNull("vector '$name' did not build", v)
            assertEquals(24f, v!!.viewportWidth)
            assertEquals(24f, v.viewportHeight)
        }
        assertNull(Glyphs.vector("no-such-glyph"))
        assertNull(Glyphs.vector(""))
    }

    @Test
    fun vector_is_parsed_once_and_cached() {
        assertSame(Glyphs.vector("water"), Glyphs.vector("water"))
    }

    @Test
    fun known_glyph_wins_over_kind_default() {
        assertSame(Glyphs.vector("water"), Glyphs.resolve("water", "doors"))
        assertSame(Glyphs.vector("fire"), Glyphs.resolve("fire", "climate"))
        // A known glyph needs no kind at all.
        assertSame(Glyphs.vector("fire"), Glyphs.resolve("fire", ""))
    }

    @Test
    fun unknown_glyph_resolves_kind_default() {
        assertSame(Glyphs.vector("water-outline"), Glyphs.resolve("mdi-from-the-future", "water"))
        assertSame(Glyphs.vector("door"), Glyphs.resolve("", "doors"))
        assertSame(Glyphs.vector("history"), Glyphs.resolve("", "timeline"))
    }

    @Test
    fun nameFor_is_the_glyph_that_resolve_draws() {
        assertEquals("water", Glyphs.nameFor("water", "doors"))
        assertEquals("water-outline", Glyphs.nameFor("mdi-from-the-future", "water"))
        // The name, not just the vector, falls back, so the card accent follows the drawn glyph.
        assertEquals("washing-machine", Glyphs.nameFor("", "laundry"))
        assertEquals("", Glyphs.nameFor("mdi-from-the-future", "no-such-kind"))
        assertEquals("", Glyphs.nameFor("", ""))
    }

    @Test
    fun unknown_kind_and_glyph_null() {
        assertNull(Glyphs.resolve("mdi-from-the-future", "no-such-kind"))
        assertNull(Glyphs.resolve("", ""))
        assertNull(Glyphs.resolve("", "no-such-kind"))
    }

    @Test
    fun defaultFor_table() {
        val table = mapOf(
            "doors" to "door",
            "laundry" to "washing-machine",
            "water" to "water-outline",
            "energy" to "flash",
            "gas" to "meter-gas",
            "climate" to "thermostat",
            "weather" to "weather-partly-cloudy",
            "calendar" to "calendar",
            "timeline" to "history",
        )
        for ((kind, glyph) in table) assertEquals("kind '$kind'", glyph, Glyphs.defaultFor(kind))
        // Every default is a shipped glyph, so resolve() can always draw a known kind.
        for (glyph in table.values) assertNotNull(Glyphs.vector(glyph))
        assertEquals("", Glyphs.defaultFor("no-such-kind"))
        assertEquals("", Glyphs.defaultFor(""))
    }
}
