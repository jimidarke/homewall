package io.haku.tablet.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.haku.tablet.data.Detail
import io.haku.tablet.data.DetailBlock
import io.haku.tablet.data.ForecastDay
import io.haku.tablet.data.RowItem
import io.haku.tablet.data.StatItem
import io.haku.tablet.ui.glyph.Glyph
import io.haku.tablet.ui.text.FitText
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType

/** Vertical gap between blocks, and horizontal gap between the columns of a block. */
internal const val BLOCK_GAP_DP = 16f
private val BlockGap = BLOCK_GAP_DP.dp
private val ColumnGap = 12.dp
private val RowsGap = 24.dp

/** The two-column layout (the weather panel): the left column's share of the width, the right's, and the gap. */
private const val LEFT_WEIGHT = 0.375f
private const val RIGHT_WEIGHT = 0.625f
private val ColumnsGap = 24.dp

private val ForecastGlyph = 72.dp
private val RowGlyph = 24.dp
private val RowGlyphSlot = 34.dp

/** Floor for text that shrinks to fit its column (the app-wide minimum). */
private val FitMin = 16.sp

/** Row slots, fixed so a block can count whole rows before composing any (like AgendaCard's). */
internal const val ROW_DP = 32f
internal const val ROW_WITH_SUB_DP = 48f
internal const val ROWS_TITLE_DP = 28f

/** Most `rows` blocks shown side by side; the rest wrap onto a further line of columns. */
internal const val MAX_ROW_COLUMNS = 3

/** A row with a `sub` takes a second line under its label. */
internal fun rowHeightDp(item: RowItem): Float = if (item.sub != null) ROW_WITH_SUB_DP else ROW_DP

/** How many of [items] fit, in order, in [availableDp]: whole rows only, never a cut-off one. */
internal fun visibleRows(items: List<RowItem>, availableDp: Float): Int {
    var used = 0f
    var n = 0
    for (item in items) {
        val h = rowHeightDp(item)
        if (used + h > availableDp + 0.01f) break   // a hair of slack, so px rounding never costs a row
        used += h
        n++
    }
    return n
}

/** "12° / 4°", or whichever of the two exists; null when neither does. */
internal fun hiLo(hi: String?, lo: String?): String? = when {
    hi != null && lo != null -> "$hi / $lo"
    else -> hi ?: lo
}

/**
 * Groups [blocks] for layout, in order. Consecutive `rows` blocks share a group, up to [MAX_ROW_COLUMNS] of
 * them, and sit side by side; every other block is a group of one.
 */
internal fun groupBlocks(blocks: List<DetailBlock>): List<List<DetailBlock>> {
    val groups = ArrayList<MutableList<DetailBlock>>()
    for (b in blocks) {
        val last = groups.lastOrNull()
        if (b is DetailBlock.Rows && last != null && last.first() is DetailBlock.Rows && last.size < MAX_ROW_COLUMNS) {
            last += b
        } else {
            groups += mutableListOf(b)
        }
    }
    return groups
}

/** How a detail's blocks are arranged: stacked in one column, or in two when the sidecar filled both. */
internal sealed interface BodyLayout {
    data class Single(val blocks: List<DetailBlock>) : BodyLayout
    data class Two(val left: List<DetailBlock>, val right: List<DetailBlock>) : BodyLayout
}

/** Two columns only when both have blocks; a payload with blocks on one side only stacks, as it always has. */
internal fun bodyLayout(detail: Detail): BodyLayout =
    if (detail.blocks.isNotEmpty() && detail.right.isNotEmpty()) BodyLayout.Two(detail.blocks, detail.right)
    else BodyLayout.Single(detail.blocks + detail.right)

/** The weather panel's left column: the hero, the facts (whatever rows fit) and the outlook, with a gap between. */
internal fun factsHeightDp(bodyDp: Float, outlookDays: Int): Float =
    bodyDp - NOW_DP - outlookDays * OUTLOOK_ROW_DP - 2 * BLOCK_GAP_DP

/**
 * The detail's blocks stacked in order with an even gap, and its `note` small under them. Give it a bounded
 * height: a chart takes whatever the other blocks leave. With no chart, forecast and `rows` blocks share that
 * height instead, `rows` blocks side by side in equal columns (up to 3 across), each showing the whole rows
 * that fit. When the sidecar put blocks in both columns (`col`), they are two columns of that, 3:5, and the
 * note goes under the right one. Everything is shown as the sidecar formatted it.
 */
@Composable
fun DetailBody(detail: Detail, modifier: Modifier = Modifier) {
    val layout = remember(detail.blocks, detail.right) { bodyLayout(detail) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(BlockGap)) {
        when (layout) {
            is BodyLayout.Single -> {
                Blocks(layout.blocks)
                Note(detail.note)
            }
            is BodyLayout.Two -> Row(Modifier.fillMaxWidth().weight(1f), horizontalArrangement = Arrangement.spacedBy(ColumnsGap)) {
                Column(Modifier.weight(LEFT_WEIGHT).fillMaxHeight(), verticalArrangement = Arrangement.spacedBy(BlockGap)) {
                    Blocks(layout.left)
                }
                Column(Modifier.weight(RIGHT_WEIGHT).fillMaxHeight(), verticalArrangement = Arrangement.spacedBy(BlockGap)) {
                    Blocks(layout.right)
                    Note(detail.note)
                }
            }
        }
    }
}

/** [blocks] in order; a chart takes the height the others leave, and `rows` share it when there is no chart. */
@Composable
private fun ColumnScope.Blocks(blocks: List<DetailBlock>) {
    val groups = remember(blocks) { groupBlocks(blocks) }
    val hasChart = remember(blocks) { blocks.any { it is DetailBlock.Chart } }
    for (group in groups) {
        when (val block = group.first()) {
            is DetailBlock.Stats -> StatsBlock(block.items)
            is DetailBlock.Days -> DaysBlock(block.items)
            is DetailBlock.Chart -> ChartBlock(block, Modifier.weight(1f))
            is DetailBlock.Forecast ->
                if (block.compact) OutlookBlock(block.days)
                else ForecastBlock(block.days, if (hasChart) Modifier else Modifier.weight(1f))
            is DetailBlock.Rows ->
                RowsGroup(group.filterIsInstance<DetailBlock.Rows>(), Modifier.weight(if (hasChart) 0.6f else 1f))
            is DetailBlock.Now -> NowBlock(block)
            is DetailBlock.Hourly -> HourlyBlock(block.items)
        }
    }
}

@Composable
private fun Note(note: String?) {
    if (note != null) {
        Text(note, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** A row of up to 6 equal columns: the label (muted), the value big, and the optional sub under it. */
@Composable
fun StatsBlock(items: List<StatItem>, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(ColumnGap)) {
        for (item in items) {
            Column(Modifier.weight(1f)) {
                Text(item.label, style = HakuType.cardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis)
                FitText(item.value, HakuType.state, minSize = FitMin, color = Haku.ink)
                if (item.sub != null) {
                    Text(item.sub, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

/** Equal columns, centred: the day's label (muted), its value, and the optional sub. */
@Composable
fun DaysBlock(items: List<StatItem>, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(ColumnGap)) {
        for (item in items) {
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    item.label, style = HakuType.cardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
                )
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    FitText(item.value, HakuType.sub, minSize = FitMin, color = Haku.ink)
                }
                if (item.sub != null) {
                    Text(
                        item.sub, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

/**
 * Equal columns, centred as a group in the height it is given: the day, a 72 dp weather glyph in ink (an
 * unknown glyph falls back to the weather default), the condition, "hi / lo" and the optional sub.
 */
@Composable
fun ForecastBlock(days: List<ForecastDay>, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(ColumnGap),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        for (day in days) {
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(day.label, style = HakuType.state, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(8.dp))
                Glyph(day.glyph, kind = "weather", tint = Haku.ink, size = ForecastGlyph)
                Spacer(Modifier.height(8.dp))
                Text(
                    day.cond, style = HakuType.sub, color = Haku.inkMuted, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
                )
                val temps = hiLo(day.hi, day.lo)
                if (temps != null) {
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        FitText(temps, HakuType.hero, minSize = FitMin, color = Haku.ink)
                    }
                }
                if (day.sub != null) {
                    Text(
                        day.sub, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

/** One to [MAX_ROW_COLUMNS] `rows` blocks side by side in equal columns, each as tall as the group. */
@Composable
private fun RowsGroup(blocks: List<DetailBlock.Rows>, modifier: Modifier) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(RowsGap)) {
        for (b in blocks) RowsBlock(b.title, b.items, Modifier.weight(1f).fillMaxHeight())
    }
}

/**
 * A titled list that never scrolls: as many whole rows as fit the height it is given, the rest left off. A row
 * is its label (left) and value (right) on one line, with the sub under the label when it has one. A glyph, in
 * its tone, goes in a slot on the left; the slot is kept for every row once any row has a glyph, so labels line up.
 */
@Composable
fun RowsBlock(title: String?, items: List<RowItem>, modifier: Modifier = Modifier) {
    val glyphSlot = items.any { it.glyph != null }
    Column(modifier) {
        if (title != null) {
            Box(Modifier.fillMaxWidth().height(ROWS_TITLE_DP.dp), contentAlignment = Alignment.CenterStart) {
                Text(title, style = HakuType.cardTitle, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
            val n = visibleRows(items, maxHeight.value)
            Column {
                for (i in 0 until n) DetailRow(items[i], glyphSlot)
            }
        }
    }
}

@Composable
private fun DetailRow(item: RowItem, glyphSlot: Boolean) {
    Row(Modifier.fillMaxWidth().height(rowHeightDp(item).dp), verticalAlignment = Alignment.CenterVertically) {
        if (glyphSlot) {
            Box(Modifier.width(RowGlyphSlot), contentAlignment = Alignment.CenterStart) {
                if (item.glyph != null) Glyph(item.glyph, kind = "", tint = toneColor(item.tone), size = RowGlyph)
            }
        }
        Column(Modifier.weight(1f)) {
            // The value is measured first, so a long label ellipsizes before the value does.
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    item.label, style = HakuType.agendaTitle, color = Haku.ink, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Text(item.value, style = HakuType.agendaTitle, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (item.sub != null) {
                Text(item.sub, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}
