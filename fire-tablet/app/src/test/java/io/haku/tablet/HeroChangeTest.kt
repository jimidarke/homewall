package io.haku.tablet

import io.haku.tablet.ui.motion.heroChangeAnimates
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HeroChangeTest {
    @Test
    fun digit_only_changes_do_not_animate() {
        // Live readings tick between polls while the house is quiet: they swap in place.
        assertFalse(heroChangeAnimates("1.1 kW", "1.2 kW"))
        assertFalse(heroChangeAnimates("Washer 34m left", "Washer 33m left"))
        assertFalse(heroChangeAnimates("57 L", "58 L"))
        assertFalse(heroChangeAnimates("9.9 kW", "10.1 kW"))
        assertFalse(heroChangeAnimates("1,234 L", "1,240 L"))
        assertFalse(heroChangeAnimates("0.0 m³/h", "1.2 m³/h"))
    }

    @Test
    fun word_or_shape_changes_animate() {
        assertTrue(heroChangeAnimates("Back open", "All closed"))
        assertTrue(heroChangeAnimates("Washer 1m left", "Washer done"))
        assertTrue(heroChangeAnimates("—", "21°"))
        assertTrue(heroChangeAnimates("21°", "—"))
        assertTrue(heroChangeAnimates("57 L", "57 L/min"))
        assertTrue(heroChangeAnimates("34m left", "1h 2m left"))
    }

    @Test
    fun equal_strings_do_not_animate() {
        assertFalse(heroChangeAnimates("1.1 kW", "1.1 kW"))
        assertFalse(heroChangeAnimates("All closed", "All closed"))
        assertFalse(heroChangeAnimates("", ""))
    }
}
