package io.haku.tablet

import io.haku.tablet.ui.detail.toneColor
import io.haku.tablet.ui.theme.Haku
import org.junit.Assert.assertEquals
import org.junit.Test

class ToneTest {
    @Test
    fun every_contract_key_maps_to_its_token() {
        assertEquals(Haku.water, toneColor("water"))
        assertEquals(Haku.heat, toneColor("heat"))
        assertEquals(Haku.cool, toneColor("cool"))
        assertEquals(Haku.washer, toneColor("washer"))
        assertEquals(Haku.dryer, toneColor("dryer"))
        assertEquals(Haku.sage, toneColor("sage"))
        assertEquals(Haku.ink, toneColor("ink"))
        assertEquals(Haku.inkMuted, toneColor("muted"))
        assertEquals(Haku.amber, toneColor("amber"))
        assertEquals(Haku.coral, toneColor("coral"))
    }

    @Test
    fun an_unknown_blank_or_missing_key_is_ink() {
        assertEquals(Haku.ink, toneColor(null))
        assertEquals(Haku.ink, toneColor(""))
        assertEquals(Haku.ink, toneColor("magenta"))
        assertEquals("keys are exact, not case-folded", Haku.ink, toneColor("Water"))
        assertEquals(Haku.ink, toneColor(" water"))
    }
}
