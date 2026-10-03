package io.haku.tablet.ui.cards

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.haku.tablet.data.AgendaItem
import io.haku.tablet.ui.glyph.Glyph
import io.haku.tablet.ui.glyph.Glyphs
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import io.haku.tablet.ui.theme.accentFor
import io.haku.tablet.ui.theme.itemAccent
import io.haku.tablet.ui.theme.parseColor

/** Fixed row heights, so the card can count whole rows before composing any. */
const val ACTIVITY_ROW_DP = 48f
const val DAY_ROW_DP = 22f
const val EVENT_ROW_DP = 26f

private val MarkSlot = 24.dp
private val Dot = 10.dp
private val ItemGlyph = 22.dp

/** New activity row (Contract 3.4): the row's accent at 0.20 behind it, fading out over 4 s. */
private const val HIGHLIGHT_MS = 4000
private const val HIGHLIGHT_ALPHA = 0.20f

/** The highlight reaches a little past the row's sides, into the card's padding, so the glyph isn't on its edge. */
private val HighlightBleed = 6.dp
private val HighlightRadius = 10.dp

internal fun AgendaItem.isDay() = kind == "header"

private fun rowHeightDp(item: AgendaItem, activity: Boolean): Float = when {
    activity -> ACTIVITY_ROW_DP
    item.isDay() -> DAY_ROW_DP
    else -> EVENT_ROW_DP
}

/**
 * How many of [items] fit, in order, in [availableDp]: whole rows only, never a cut-off one. A day header
 * is never the last row shown, since it would head nothing.
 */
fun visibleRowCount(items: List<AgendaItem>, activity: Boolean, availableDp: Float): Int {
    var used = 0f
    var n = 0
    for (item in items) {
        val h = rowHeightDp(item, activity)
        if (used + h > availableDp) break
        used += h
        n++
    }
    while (n > 0 && items[n - 1].isDay()) n--
    return n
}

/**
 * Whether an Activity row timed [itemWhen] is new since the previous good poll, whose newest item was
 * [highlightAfter] (both epoch seconds). Null after a gap or at cold start, so nothing is new then.
 */
fun isHighlighted(itemWhen: Long?, highlightAfter: Long?): Boolean =
    itemWhen != null && highlightAfter != null && itemWhen > highlightAfter

/** The sidecar's upper-case day header ("WED · OCT 7") as "Wed · Oct 7". */
fun dayLabel(header: String): String =
    header.split(" ").joinToString(" ") { w -> w.lowercase().replaceFirstChar { it.titlecase() } }

/**
 * A list card that never scrolls: as many whole rows as fit, the rest left off. The Activity feed shows a
 * glyph, title and "sub · time" per row, and a row new since the previous good poll ([isHighlighted]) lights
 * up in its accent and fades over 4 s. The calendar shows day headers and one-line events. Agenda cards take
 * no active or alert styling.
 */
@Composable
fun AgendaCard(m: AgendaModel, modifier: Modifier = Modifier) {
    val glyph = Glyphs.nameFor(m.glyph, m.kind)
    val chrome = CardChrome(
        title = m.title, glyph = glyph, kind = m.kind, accent = accentFor(glyph),
        active = false, alert = false, stale = m.stale,
    )
    GlassCard(chrome, modifier) {
        if (m.items.isEmpty()) {
            Text("Nothing yet", style = HakuType.detail, color = Haku.inkMuted)
        } else {
            BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
                val n = visibleRowCount(m.items, m.activity, maxHeight.value)
                Column {
                    for (i in 0 until n) {
                        val item = m.items[i]
                        when {
                            // Keyed by the item, so a row keeps its highlight as newer rows push it down.
                            m.activity -> key(item.whenTs, item.title) {
                                ActivityRow(item, isNew = isHighlighted(item.whenTs, m.highlightAfter))
                            }
                            item.isDay() -> DayRow(item)
                            else -> EventRow(item)
                        }
                    }
                }
            }
        }
    }
}

/**
 * One Activity row. [isNew] counts only when the row first appears: it then starts lit and fades out, and
 * the next poll (when it is no longer new) leaves the fade running. The fade is read only while drawing.
 */
@Composable
internal fun ActivityRow(item: AgendaItem, isNew: Boolean) {
    val accent = itemAccent(item.glyph)
    val highlight = remember { Animatable(if (isNew) 1f else 0f) }
    LaunchedEffect(highlight) {
        if (highlight.value > 0f) highlight.animateTo(0f, tween(HIGHLIGHT_MS))
    }
    Row(
        Modifier
            .fillMaxWidth()
            .height(ACTIVITY_ROW_DP.dp)
            .drawWithCache {
                val bleed = HighlightBleed.toPx()
                val corner = CornerRadius(HighlightRadius.toPx())
                val box = Size(size.width + 2 * bleed, size.height)
                onDrawBehind {
                    val h = highlight.value
                    if (h > 0f) {
                        drawRoundRect(accent, Offset(-bleed, 0f), box, corner, alpha = HIGHLIGHT_ALPHA * h)
                    }
                }
            },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(MarkSlot), contentAlignment = Alignment.Center) {
            if (Glyphs.vector(item.glyph) != null) {
                Glyph(item.glyph, kind = "", tint = accent, size = ItemGlyph)
            } else {
                Box(Modifier.size(Dot).background(accent, CircleShape))
            }
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(item.title, style = HakuType.agendaTitle, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val meta = listOf(item.sub, item.time).filter { it.isNotBlank() }.joinToString(" · ")
            Text(meta, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
internal fun DayRow(item: AgendaItem) {
    Box(Modifier.fillMaxWidth().height(DAY_ROW_DP.dp), contentAlignment = Alignment.BottomStart) {
        Text(dayLabel(item.title), style = HakuType.detail, color = Haku.sage, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
internal fun EventRow(item: AgendaItem) {
    Row(Modifier.fillMaxWidth().height(EVENT_ROW_DP.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(Dot).background(parseColor(item.dot), CircleShape))
        Spacer(Modifier.width(10.dp))
        Text(
            item.title,
            style = HakuType.agendaTitle,
            color = Haku.ink,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        if (item.time.isNotBlank()) {
            Spacer(Modifier.width(8.dp))
            Text(item.time, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1)
        }
    }
}
