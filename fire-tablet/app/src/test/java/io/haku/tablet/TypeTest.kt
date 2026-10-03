package io.haku.tablet

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.sp
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TypeTest {
    private val all = mapOf(
        "clock" to HakuType.clock, "date" to HakuType.date, "hero" to HakuType.hero, "state" to HakuType.state,
        "sub" to HakuType.sub, "agendaTitle" to HakuType.agendaTitle, "detail" to HakuType.detail,
        "cardTitle" to HakuType.cardTitle,
    )

    @Test
    fun sizes_match_contract() {
        assertEquals(40.sp, HakuType.clock.fontSize)
        assertEquals(20.sp, HakuType.date.fontSize)
        assertEquals(44.sp, HakuType.hero.fontSize)
        assertEquals(26.sp, HakuType.state.fontSize)
        assertEquals(20.sp, HakuType.sub.fontSize)
        assertEquals(18.sp, HakuType.agendaTitle.fontSize)
        assertEquals(16.sp, HakuType.detail.fontSize)
        assertEquals(16.sp, HakuType.cardTitle.fontSize)
    }

    @Test
    fun nothing_is_below_16sp() {
        for ((name, style) in all) assertTrue("$name is ${style.fontSize}", style.fontSize.value >= 16f)
    }

    @Test
    fun numeric_styles_use_tabular_figures() {
        for ((name, style) in all - "cardTitle") assertEquals("$name tnum", "tnum", style.fontFeatureSettings)
    }

    @Test
    fun hero_has_fixed_line_height_trimmed_both_ends() {
        assertEquals(44.sp, HakuType.hero.lineHeight)
        assertEquals(
            LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.Both),
            HakuType.hero.lineHeightStyle,
        )
    }

    @Test
    fun card_title_is_muted_and_every_style_has_a_face() {
        assertEquals(Haku.inkMuted, HakuType.cardTitle.color)
        for ((name, style) in all) assertNotNull("$name font family", style.fontFamily)
        // Colour comes from the call site (FitText / Text), except the muted card title.
        assertTrue(all.filterKeys { it != "cardTitle" }.values.all { it.color == Color.Unspecified })
    }
}
