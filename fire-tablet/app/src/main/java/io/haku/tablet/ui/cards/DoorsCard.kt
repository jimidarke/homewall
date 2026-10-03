package io.haku.tablet.ui.cards

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.haku.tablet.data.Door
import io.haku.tablet.ui.glyph.Glyph
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType

private const val MAX_DOORS = 3

private val RowHeight = 42.dp
private val RowGap = 8.dp
private val DoorGlyph = 32.dp

/**
 * The state word's and the age's slots. Each holds its text bottom-aligned and lets the text's empty
 * ascent rise above the slot, so the age tucks under the state word without the two colliding.
 */
private val StateSlot = 26.dp
private val AgeSlot = 16.dp

/**
 * One row per door, up to three, as many whole rows as fit (two on a 1×1 tile), open and unknown doors first
 * ([doorsShown]): the door's glyph and label, and on the right its state word over its age. Closed is ink,
 * open amber (coral once the sidecar says it has been open too long), unknown grey. With no doors it shows
 * the summary tile instead.
 */
@Composable
fun DoorsCard(m: DoorsModel, modifier: Modifier = Modifier) {
    if (m.doors.isEmpty()) {
        ValueCard(m.base, modifier)
        return
    }
    GlassCard(m.base.chrome(), modifier) {
        BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
            val fit = ((maxHeight + RowGap) / (RowHeight + RowGap)).toInt()
            Column(verticalArrangement = Arrangement.spacedBy(RowGap)) {
                doorsShown(m.doors, fit).forEach { DoorRow(it) }
            }
        }
    }
}

/**
 * The doors a card with room for [fit] rows shows: open and unknown ones before closed ones, so a short tile
 * can never cut off an open door. The sort is stable, so each group keeps the sidecar's order.
 */
internal fun doorsShown(doors: List<Door>, fit: Int): List<Door> =
    doors.sortedBy { it.state == "closed" }.take(minOf(MAX_DOORS, fit))

@Composable
private fun DoorRow(door: Door) {
    val (word, color) = when (door.state) {
        "open" -> "Open" to if (door.severity == "high") Haku.coral else Haku.amber
        "closed" -> "Closed" to Haku.ink
        else -> "Unknown" to Haku.offline
    }
    // The glyph is coloured like the word, except that a closed door stays as muted as a resting chip.
    val glyphTint = if (door.state == "closed") Haku.inkMuted else color
    Row(Modifier.fillMaxWidth().height(RowHeight)) {
        Glyph(
            door.glyph, kind = "doors", tint = glyphTint, size = DoorGlyph,
            modifier = Modifier.align(Alignment.CenterVertically),
        )
        Spacer(Modifier.width(10.dp))
        Text(
            door.label, style = HakuType.sub, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f).alignByBaseline(),
        )
        Spacer(Modifier.width(8.dp))
        Column(Modifier.alignByBaseline(), horizontalAlignment = Alignment.End) {
            Text(
                word, style = HakuType.state, color = color, maxLines = 1,
                modifier = Modifier.slot(StateSlot, Alignment.Bottom),
            )
            Text(
                door.age, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1,
                modifier = Modifier.slot(AgeSlot, Alignment.Bottom),
            )
        }
    }
}
