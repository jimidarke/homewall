package io.haku.tablet.ui.cards

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.haku.tablet.ui.glyph.Glyphs
import io.haku.tablet.ui.model.ValueModel
import io.haku.tablet.ui.motion.AnimatedHero
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import io.haku.tablet.ui.theme.accentFor

private val HeroMin = 30.sp

/** Line slots from the Contract's value-card budget (hero 44, sub 24, detail 20). */
private val HeroSlot = 44.dp
private val SubSlot = 24.dp
private val DetailSlot = 20.dp

private val BarHeight = 4.dp
private val BarRadius = 3.dp

/** The bar sits on the card's bottom edge, down in the bottom padding, clear of the detail line above. */
private val BarDrop = 4.dp

/**
 * The summary card: hero, sub and detail as the sidecar formatted them, plus a level bar when the tile
 * has a `level`. A new hero value slides in ([AnimatedHero]); only an alert colours it, cross-fading to coral
 * with the card's alert level ([CardTone.hero]). Sub and detail keep their line even when empty, so the
 * lines of neighbouring cards stay level with each other. A held card ([ValueModel.asOf]) says when its
 * reading is from on the detail line instead.
 */
@Composable
fun ValueCard(m: ValueModel, modifier: Modifier = Modifier) {
    GlassCard(m.chrome(), modifier) {
        AnimatedHero(
            text = m.hero,
            style = HakuType.hero,
            minSize = HeroMin,
            color = LocalCardTone.current.hero,
            modifier = Modifier.fillMaxWidth().slot(HeroSlot, Alignment.Bottom),
        )
        Text(
            m.sub, style = HakuType.sub, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.slot(SubSlot),
        )
        Text(
            m.asOf ?: m.detail, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.slot(DetailSlot),
        )
        if (m.level != null) {
            Spacer(Modifier.weight(1f))
            LevelBar(m.level)
        }
    }
}

/**
 * The chrome for a card driven by a summary tile (value, doors, laundry): the shipped glyph and its accent,
 * the tile's active and alert flags, and its pulse.
 */
internal fun ValueModel.chrome(): CardChrome {
    val shown = Glyphs.nameFor(glyph, kind)
    return CardChrome(
        title = title, glyph = shown, kind = kind, accent = accentFor(shown),
        active = active, alert = alert, stale = stale,
        pulseSeq = pulseSeq, pulseCount = pulseCount,
    )
}

/**
 * A fixed-height line that holds its text at [align] whatever height the text measures, so the lines
 * below never move and nothing is clipped. A one-line hero measures taller than its slot: it keeps its
 * font's full 1.2 em box (52.8 dp at 44 sp) despite its 44 sp line height. It measures shorter when
 * `FitText` shrinks it, since the box scales with the font size.
 *
 * The hero sits on the slot's bottom: the box's extra height is empty ascent above the capitals, so it
 * rises into the header row's whitespace, and a shrunken hero keeps nearly the same baseline.
 */
internal fun Modifier.slot(height: Dp, align: Alignment.Vertical = Alignment.CenterVertically): Modifier =
    height(height).wrapContentHeight(align, unbounded = true)

/**
 * A 4 dp gauge with no track, so an empty level shows nothing. Faint ink while the card is quiet; lit like
 * the chip ([CardTone]): the held accent while active, coral on alert.
 */
@Composable
private fun LevelBar(level: Int) {
    val tone = LocalCardTone.current
    val fraction = level.coerceIn(0, 100) / 100f
    Spacer(
        Modifier.fillMaxWidth().height(BarHeight).offset(y = BarDrop).drawWithCache {
            val corner = CornerRadius(BarRadius.toPx())
            val fill = Size(size.width * fraction, size.height)
            onDrawBehind {
                if (fraction > 0f) drawRoundRect(tone.over(Haku.inkFaint), size = fill, cornerRadius = corner)
            }
        },
    )
}
