package io.haku.tablet.ui.cards

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import io.haku.tablet.data.ModuleDesc
import io.haku.tablet.ui.glyph.Glyphs
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.model.CardModel
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.model.ValueModel

enum class CardKind { VALUE, DOORS, LAUNDRY, AGENDA }

/** Which card draws [m]. `project()` already sent unknown tile types to a value card. */
fun cardKind(m: CardModel): CardKind = when (m) {
    is ValueModel -> CardKind.VALUE
    is DoorsModel -> CardKind.DOORS
    is LaundryModel -> CardKind.LAUNDRY
    is AgendaModel -> CardKind.AGENDA
}

/** The card for [model]. */
@Composable
fun CardFor(model: CardModel, modifier: Modifier = Modifier) {
    when (cardKind(model)) {
        CardKind.VALUE -> ValueCard(model as ValueModel, modifier)
        CardKind.DOORS -> DoorsCard(model as DoorsModel, modifier)
        CardKind.LAUNDRY -> LaundryCard(model as LaundryModel, modifier)
        CardKind.AGENDA -> AgendaCard(model as AgendaModel, modifier)
    }
}

/**
 * What a module shows before it has a card (no good poll yet, or added by a config reload since the last
 * one): its title, its kind's glyph and a dash, so the grid never has a hole.
 */
fun placeholderCard(m: ModuleDesc): ValueModel = ValueModel(
    id = m.id,
    kind = m.kind,
    title = m.title,
    glyph = Glyphs.defaultFor(m.kind),
    hero = "—",
    sub = "",
    detail = "",
    alert = false,
    active = false,
    level = null,
    stale = false,
)
