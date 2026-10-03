package io.haku.tablet

import androidx.compose.animation.core.SpringSpec
import androidx.compose.ui.graphics.Color
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.accentFor
import io.haku.tablet.ui.theme.itemAccent
import io.haku.tablet.ui.theme.parseColor
import org.junit.Assert.assertEquals
import org.junit.Test

class TokensTest {
    private val rose = Color(0xFFFF8040.toInt())

    @Test
    fun base_tokens_match_contract() {
        assertEquals(Color(0xFFFAF6EE), Haku.ink)
        assertEquals(Haku.ink.copy(alpha = 0.78f), Haku.inkMuted)
        assertEquals(Haku.ink.copy(alpha = 0.48f), Haku.inkFaint)
        assertEquals(Color(0xFF0C1211), Haku.night)
        assertEquals(Color(0xFF5B8C7F), Haku.sage)
        assertEquals(Color(0xFFD4673E), Haku.coral)
        assertEquals(Color(0xFFD9A441), Haku.amber)
        assertEquals(Color(0xFF6E7471), Haku.offline)
    }

    @Test
    fun accent_tokens_match_contract() {
        assertEquals(Color(0xFF4FB3E8), Haku.water)
        assertEquals(Color(0xFFF2994A), Haku.heat)
        assertEquals(Color(0xFF7CCBF2), Haku.cool)
        assertEquals(Color(0xFF00AAFF), Haku.washer)
        assertEquals(Color(0xFFFF6900), Haku.dryer)
        assertEquals(Color(0xFFE5484D), Haku.ledIdleRed)
        assertEquals(Color(0xFF9B7BEA), Haku.ledStaleViolet)
    }

    @Test
    fun springs_match_contract() {
        val slow: SpringSpec<Float> = Haku.effectsSlow()
        assertEquals(1f, slow.dampingRatio)
        assertEquals(800f, slow.stiffness)
        val standard: SpringSpec<Float> = Haku.spatialStandard()
        assertEquals(0.9f, standard.dampingRatio)
        assertEquals(700f, standard.stiffness)
    }

    @Test
    fun parseColor_hash_rgb() {
        assertEquals(Color(0xFF5B8C7F), parseColor("#5B8C7F"))
        assertEquals(Color(0xFF5B8C7F), parseColor("#5b8c7f"))
    }

    @Test
    fun parseColor_hash_argb() {
        assertEquals(Color(0x805B8C7F), parseColor("#805B8C7F"))
        assertEquals(Color(0x00FF0000), parseColor("#00ff0000"))
    }

    @Test
    fun parseColor_roku_0xRRGGBBAA() {
        // Opaque: the issue's example. The trailing byte is alpha, not blue.
        assertEquals(Color(0xFF5B8C7F), parseColor("0x5B8C7FFF"))
        // Partial alpha moves to the front; case-insensitive in both the prefix and the digits.
        assertEquals(Color(0x80FF8040), parseColor("0xFF804080"))
        assertEquals(Color(0xFFFF8040), parseColor("0Xff8040ff"))
    }

    @Test
    fun parseColor_garbage_falls_back() {
        for (bad in listOf("", "#", "red", "5B8C7F", "#5B8C7", "#5B8C7FF", "#GGGGGG", "#-5B8C7", "#+5B8C7", "0x5B8C7F", "0x5B8C7FFFFF", "0xZZZZZZZZ", " #5B8C7F")) {
            assertEquals("input '$bad'", Haku.sage, parseColor(bad))
        }
        assertEquals(rose, parseColor("nope", rose))
        // A valid colour ignores the fallback.
        assertEquals(Color(0xFF5B8C7F), parseColor("#5B8C7F", rose))
    }

    @Test
    fun accentFor_table() {
        assertEquals(Haku.amber, accentFor("door-open"))
        assertEquals(Haku.water, accentFor("water"))
        assertEquals(Haku.heat, accentFor("fire"))
        assertEquals(Haku.cool, accentFor("snowflake"))
        assertEquals(Haku.sage, accentFor("fan"))
        assertEquals(Haku.washer, accentFor("washing-machine"))
        assertEquals(Haku.dryer, accentFor("tumble-dryer"))
        // Anything else is sage: closed door, idle water, other kinds, empty and unknown names.
        for (other in listOf("door-closed", "water-outline", "flash", "meter-gas", "thermostat", "calendar", "", "no-such-glyph")) {
            assertEquals("glyph '$other'", Haku.sage, accentFor(other))
        }
    }

    @Test
    fun itemAccent_table() {
        assertEquals(Haku.amber, itemAccent("door-open"))
        assertEquals(Haku.amber, itemAccent("lock-open-variant"))
        assertEquals(Haku.sage, itemAccent("home-account"))
        // Anything else is muted ink, including glyphs that are card accents.
        for (other in listOf("door-closed", "lock", "motion-sensor", "motion-sensor-off", "account-arrow-right", "water", "", "no-such-glyph")) {
            assertEquals("glyph '$other'", Haku.inkMuted, itemAccent(other))
        }
    }
}
