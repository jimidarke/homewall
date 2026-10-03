package io.haku.tablet

import androidx.compose.runtime.State
import androidx.compose.ui.graphics.lerp
import io.haku.tablet.ui.cards.CardTone
import io.haku.tablet.ui.theme.Haku
import org.junit.Assert.assertEquals
import org.junit.Test

class CardToneTest {
    private class Fixed(override val value: Float) : State<Float>

    private fun tone(act: Float, alert: Float) = CardTone(Haku.water, Fixed(act), Fixed(alert))

    @Test
    fun quiet_card_is_unlit_and_muted() {
        val t = tone(act = 0f, alert = 0f)
        assertEquals(0f, t.lit)
        assertEquals(Haku.inkMuted, t.over(Haku.inkMuted))
        assertEquals(Haku.inkFaint, t.over(Haku.inkFaint))
    }

    @Test
    fun active_card_takes_its_accent() {
        val t = tone(act = 1f, alert = 0f)
        assertEquals(1f, t.lit)
        assertEquals(Haku.water, t.tone)
        assertEquals(Haku.water, t.over(Haku.inkFaint))
    }

    @Test
    fun alert_lights_the_card_coral_even_when_idle() {
        // Energy over its threshold is an alert but never active: its chip, glyph and bar still go coral.
        val idle = tone(act = 0f, alert = 1f)
        assertEquals(1f, idle.lit)
        assertEquals(Haku.coral, idle.tone)
        assertEquals(Haku.coral, idle.over(Haku.inkMuted))
        // And an alert overrides the accent of an active card.
        assertEquals(Haku.coral, tone(act = 1f, alert = 1f).over(Haku.inkFaint))
    }

    @Test
    fun lit_is_the_stronger_of_active_and_alert_mid_fade() {
        assertEquals(0.6f, tone(act = 0.6f, alert = 0.25f).lit)
        assertEquals(0.7f, tone(act = 0.2f, alert = 0.7f).lit)
        // Half way into an alert, the tone is half way (Compose's colour lerp) from the accent to coral.
        assertEquals(lerp(Haku.water, Haku.coral, 0.5f), tone(act = 1f, alert = 0.5f).tone)
    }
}
