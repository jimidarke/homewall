package io.haku.tablet

import io.haku.tablet.data.AgendaItem
import io.haku.tablet.ui.cards.ACTIVITY_ROW_DP
import io.haku.tablet.ui.cards.DAY_ROW_DP
import io.haku.tablet.ui.cards.EVENT_ROW_DP
import io.haku.tablet.ui.cards.dayLabel
import io.haku.tablet.ui.cards.visibleRowCount
import org.junit.Assert.assertEquals
import org.junit.Test

class AgendaRowsTest {
    private fun event(title: String) = AgendaItem(kind = "event", title = title, sub = "", time = "", severity = "normal")
    private fun day(title: String) = AgendaItem(kind = "header", title = title, sub = "", time = "", severity = "normal")

    @Test
    fun day_label_is_title_cased_per_word() {
        assertEquals("Today", dayLabel("TODAY"))
        assertEquals("Tomorrow", dayLabel("TOMORROW"))
        assertEquals("Wed · Oct 7", dayLabel("WED · OCT 7"))
        assertEquals("Fri · Oct 2", dayLabel("FRI · OCT 2"))
        assertEquals("", dayLabel(""))
    }

    @Test
    fun activity_shows_only_whole_48dp_rows() {
        val items = List(20) { event("e$it") }
        assertEquals(9, visibleRowCount(items, activity = true, availableDp = 458f))
        assertEquals(9, visibleRowCount(items, activity = true, availableDp = 9 * ACTIVITY_ROW_DP))
        assertEquals(8, visibleRowCount(items, activity = true, availableDp = 9 * ACTIVITY_ROW_DP - 0.5f))
        assertEquals(0, visibleRowCount(items, activity = true, availableDp = ACTIVITY_ROW_DP - 1f))
        assertEquals(3, visibleRowCount(items.take(3), activity = true, availableDp = 458f))
    }

    @Test
    fun calendar_mixes_day_and_event_heights() {
        val items = listOf(day("TODAY"), event("a"), day("TOMORROW"), event("b"), event("c"))
        // A 1x1 agenda card on the 4x3 grid has about 96.7 dp under its header row.
        assertEquals(4, visibleRowCount(items, activity = false, availableDp = 96.67f))
        assertEquals(5, visibleRowCount(items, activity = false, availableDp = 2 * DAY_ROW_DP + 3 * EVENT_ROW_DP))
    }

    @Test
    fun two_tall_calendar_shows_four_days() {
        // The 2-tall calendar (351.3 dp) has about 277.3 dp under its header row: the busy demo's four days fit.
        val week = listOf("TODAY", "TOMORROW", "FRI · OCT 2", "MON · OCT 5").flatMap { listOf(day(it), event(it)) }
        assertEquals(8, visibleRowCount(week, activity = false, availableDp = 277.3f))
        // A long live calendar stops on whole rows and never on a day header.
        val long = week + week + week
        val n = visibleRowCount(long, activity = false, availableDp = 277.3f)
        // 5 days with their events fill 240 dp. A 6th day header fits (262) but its event would not (288),
        // so that header is left off too.
        assertEquals(10, n)
        assertEquals("event", long[n - 1].kind)
    }

    @Test
    fun calendar_never_ends_on_a_day_header() {
        val items = listOf(day("TODAY"), event("a"), day("TOMORROW"), event("b"))
        // Room for today, its event and tomorrow's header, but not tomorrow's event: the header goes too.
        assertEquals(2, visibleRowCount(items, activity = false, availableDp = 2 * DAY_ROW_DP + EVENT_ROW_DP + 1f))
        // A day header alone shows nothing at all.
        assertEquals(0, visibleRowCount(listOf(day("TODAY")), activity = false, availableDp = 200f))
    }

    @Test
    fun empty_or_no_room_shows_nothing() {
        assertEquals(0, visibleRowCount(emptyList(), activity = false, availableDp = 200f))
        assertEquals(0, visibleRowCount(listOf(event("a")), activity = false, availableDp = 0f))
        assertEquals(0, visibleRowCount(listOf(event("a")), activity = false, availableDp = -5f))
    }
}
