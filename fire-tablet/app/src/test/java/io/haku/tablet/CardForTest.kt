package io.haku.tablet

import io.haku.tablet.data.HubJson
import io.haku.tablet.data.ModuleDesc
import io.haku.tablet.data.TileSpec
import io.haku.tablet.ui.cards.CardKind
import io.haku.tablet.ui.cards.cardKind
import io.haku.tablet.ui.cards.placeholderCard
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.model.ValueModel
import io.haku.tablet.ui.model.project
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File

class CardForTest {
    private val demoDir = File("src/debug/assets/demo")

    private fun value(id: String) = ValueModel(
        id = id, kind = "water", title = "Water", glyph = "water", hero = "57 L", sub = "", detail = "",
        alert = false, active = false, level = null, stale = false,
    )

    @Test
    fun cardKind_dispatch() {
        assertEquals(CardKind.VALUE, cardKind(value("w")))
        assertEquals(CardKind.DOORS, cardKind(DoorsModel(value("d"), emptyList())))
        assertEquals(CardKind.LAUNDRY, cardKind(LaundryModel(value("l"), emptyList())))
        val agenda = AgendaModel(
            id = "t", kind = "timeline", title = "Activity", glyph = "history", items = emptyList(),
            activity = true, stale = false, highlightAfter = null,
        )
        assertEquals(CardKind.AGENDA, cardKind(agenda))
    }

    @Test
    fun doors_model_kind_is_doors() {
        // A projected doors card carries a value tile in `base`, but it is still a doors card.
        val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
        val state = HubJson.parseState(File(demoDir, "busy.json").readText())
        val card = project(config, state).getValue("doors")
        assertEquals(CardKind.DOORS, cardKind(card))
    }

    @Test
    fun placeholder_is_a_dash_value_card_with_the_kind_default_glyph() {
        val m = ModuleDesc(id = "water", kind = "water", title = "Water")
        val card = placeholderCard(m)
        assertEquals(CardKind.VALUE, cardKind(card))
        assertEquals("water", card.id)
        assertEquals("Water", card.title)
        assertEquals("—", card.hero)
        assertEquals("water-outline", card.glyph)
        assertEquals("", card.sub)
        assertEquals("", card.detail)
        assertNull(card.level)
        assertFalse(card.active || card.alert || card.stale)
    }

    @Test
    fun placeholder_for_an_agenda_module_is_still_a_value_card() {
        val m = ModuleDesc(id = "calendar", kind = "calendar", title = "Calendar", tile = TileSpec(type = "agenda"))
        val card = placeholderCard(m)
        assertEquals(CardKind.VALUE, cardKind(card))
        assertEquals("calendar", card.glyph)
    }
}
