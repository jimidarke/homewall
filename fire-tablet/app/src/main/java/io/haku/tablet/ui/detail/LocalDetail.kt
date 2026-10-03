package io.haku.tablet.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.haku.tablet.data.AgendaItem
import io.haku.tablet.ui.cards.ACTIVITY_ROW_DP
import io.haku.tablet.ui.cards.DAY_ROW_DP
import io.haku.tablet.ui.cards.ActivityRow
import io.haku.tablet.ui.cards.DayRow
import io.haku.tablet.ui.cards.EVENT_ROW_DP
import io.haku.tablet.ui.cards.EventRow
import io.haku.tablet.ui.cards.isDay
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import kotlin.math.max
import kotlin.math.min

/*
 * Calendar and Activity have no sidecar detail: their panel is the same list the card shows, at full width.
 */

/** Columns the list flows into: Activity always uses all of them, Calendar at least [MIN_CALENDAR_COLUMNS]. */
private const val AGENDA_COLUMNS = 4

/** Event titles are long, so a short calendar still splits over two wide columns instead of one narrow one. */
private const val MIN_CALENDAR_COLUMNS = 2
private val AgendaColumnGap = 24.dp

/**
 * How many columns a list of [itemCount] rows gets, and how many rows each holds, when [rowsFit] rows fit in a
 * column: as few columns as hold them all, at least [minColumns] and at most four, with the rows balanced
 * across them (one row of slack, for a day header that moves on to the next column).
 */
internal fun agendaGrid(itemCount: Int, rowsFit: Int, minColumns: Int): Pair<Int, Int> {
    if (rowsFit <= 0 || itemCount <= 0) return 0 to 0
    val columns = ((itemCount + rowsFit - 1) / rowsFit).coerceIn(minColumns.coerceAtMost(AGENDA_COLUMNS), AGENDA_COLUMNS)
    val rows = min(rowsFit, (itemCount + columns - 1) / columns + 1)
    return columns to rows
}

/**
 * [items] flowed down [columns] columns of [rowsPerColumn] rows each, top to bottom then left to right, in
 * order. A day header is never the last row of a column: it goes to the top of the next one, so it always
 * heads something. Items that do not fit in [columns] columns are left off, and so is a header with nothing
 * to head (the last row of the list, one followed by another header, or one in a column a single row tall).
 * Columns are never empty; fewer than [columns] come back when the items run out.
 */
fun flowColumns(items: List<AgendaItem>, rowsPerColumn: Int, columns: Int): List<List<AgendaItem>> {
    if (rowsPerColumn <= 0 || columns <= 0) return emptyList()
    val out = ArrayList<List<AgendaItem>>(min(columns, 8))
    var from = 0
    while (from < items.size && out.size < columns) {
        var to = min(from + rowsPerColumn, items.size)
        while (to > from && items[to - 1].isDay()) to--   // a header at the foot of the column moves on
        if (to == from) {   // only headers: they could head nothing in this column, so skip the first
            from++
            continue
        }
        out += items.subList(from, to).toList()
        from = to
    }
    return out
}

/**
 * A calendar or Activity list at full width: the card's own rows ([EventRow], [DayRow], [ActivityRow]) in
 * [AGENDA_COLUMNS] equal columns, as many as the height allows ([flowColumns]). Nothing animates, so a row new
 * since the last poll is not lit up. Give it a bounded height.
 */
@Composable
fun AgendaDetail(model: AgendaModel, modifier: Modifier = Modifier) {
    if (model.items.isEmpty()) {
        Text("Nothing yet", style = HakuType.detail, color = Haku.inkMuted, modifier = modifier)
        return
    }
    BoxWithConstraints(modifier.fillMaxSize()) {
        // Counted in the tallest row the list has, so a column can only come up short, never overflow.
        val rowDp = if (model.activity) ACTIVITY_ROW_DP else max(DAY_ROW_DP, EVENT_ROW_DP)
        val fit = (maxHeight.value / rowDp).toInt()
        val (count, perColumn) = agendaGrid(model.items.size, fit, if (model.activity) AGENDA_COLUMNS else MIN_CALENDAR_COLUMNS)
        val columns = remember(model.items, perColumn, count) { flowColumns(model.items, perColumn, count) }
        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(AgendaColumnGap)) {
            for (column in columns) {
                Column(Modifier.weight(1f)) {
                    for (item in column) {
                        when {
                            model.activity -> ActivityRow(item, isNew = false)
                            item.isDay() -> DayRow(item)
                            else -> EventRow(item)
                        }
                    }
                }
            }
            // A column the items didn't reach keeps its share of the width, so the rows do not stretch.
            repeat(count - columns.size) { Spacer(Modifier.weight(1f)) }
        }
    }
}
