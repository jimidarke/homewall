package io.haku.tablet

import io.haku.tablet.data.AgendaItem
import io.haku.tablet.ui.detail.flowColumns
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Random

class FlowColumnsTest {
    private fun event(title: String) = AgendaItem(kind = "event", title = title, sub = "", time = "", severity = "normal")
    private fun day(title: String) = AgendaItem(kind = "header", title = title, sub = "", time = "", severity = "normal")

    private fun titles(cols: List<List<AgendaItem>>) = cols.map { c -> c.map { it.title } }

    @Test
    fun items_flow_down_a_column_then_across() {
        val items = (0..6).map { event("e$it") }
        assertEquals(
            listOf(listOf("e0", "e1", "e2"), listOf("e3", "e4", "e5"), listOf("e6")),
            titles(flowColumns(items, rowsPerColumn = 3, columns = 4)),
        )
    }

    @Test
    fun it_stops_when_the_columns_are_full() {
        val items = (0..9).map { event("e$it") }
        assertEquals(
            listOf(listOf("e0", "e1", "e2"), listOf("e3", "e4", "e5")),
            titles(flowColumns(items, rowsPerColumn = 3, columns = 2)),
        )
    }

    @Test
    fun fewer_items_than_a_column_give_one_column_and_no_empty_ones() {
        assertEquals(listOf(listOf("e0", "e1")), titles(flowColumns(listOf(event("e0"), event("e1")), 5, 4)))
        assertTrue(flowColumns(emptyList(), 5, 4).isEmpty())
    }

    @Test
    fun a_header_that_would_end_a_column_starts_the_next_one() {
        val items = listOf(day("TODAY"), event("a"), day("TOMORROW"), event("b"), event("c"))
        assertEquals(
            listOf(listOf("TODAY", "a"), listOf("TOMORROW", "b", "c")),
            titles(flowColumns(items, rowsPerColumn = 3, columns = 4)),
        )
    }

    @Test
    fun a_header_in_the_middle_of_a_column_stays() {
        val items = listOf(day("TODAY"), event("a"), event("b"), day("TOMORROW"), event("c"))
        assertEquals(
            listOf(listOf("TODAY", "a", "b", "TOMORROW", "c")),
            titles(flowColumns(items, rowsPerColumn = 5, columns = 4)),
        )
    }

    @Test
    fun a_header_with_nothing_after_it_is_left_off() {
        val items = listOf(event("a"), event("b"), day("TOMORROW"))
        assertEquals(listOf(listOf("a", "b")), titles(flowColumns(items, 5, 4)))
        // ... even when it is exactly the last row of the last column that fits.
        assertEquals(listOf(listOf("a", "b")), titles(flowColumns(items, 3, 4)))
    }

    @Test
    fun a_header_pushed_past_the_last_column_is_dropped_with_the_rest() {
        val items = listOf(event("a"), event("b"), day("TOMORROW"), event("c"))
        assertEquals(listOf(listOf("a", "b")), titles(flowColumns(items, rowsPerColumn = 3, columns = 1)))
        assertEquals(
            listOf(listOf("a", "b"), listOf("TOMORROW", "c")),
            titles(flowColumns(items, rowsPerColumn = 3, columns = 2)),
        )
    }

    @Test
    fun a_column_one_row_tall_skips_headers_instead_of_looping() {
        val items = listOf(day("D1"), event("a"), day("D2"), event("b"))
        assertEquals(listOf(listOf("a"), listOf("b")), titles(flowColumns(items, rowsPerColumn = 1, columns = 4)))
    }

    @Test
    fun a_header_followed_by_another_heads_nothing_and_is_skipped() {
        val items = listOf(event("a"), day("D1"), day("D2"), event("b"))
        // [a, D1] ends in a header, so D1 moves on; [D1, D2] ends in one, and D1 heads only D2, so D1 is skipped.
        assertEquals(
            listOf(listOf("a"), listOf("D2", "b")),
            titles(flowColumns(items, rowsPerColumn = 2, columns = 4)),
        )
        assertEquals(
            listOf(listOf("a", "D2", "b")),
            titles(flowColumns(listOf(event("a"), day("D2"), event("b")), rowsPerColumn = 3, columns = 4)),
        )
    }

    @Test
    fun activity_items_with_no_headers_fill_every_column_exactly() {
        val items = (1..12).map { event("e$it") }
        val cols = flowColumns(items, rowsPerColumn = 3, columns = 4)
        assertEquals(listOf(3, 3, 3, 3), cols.map { it.size })
        assertEquals(items, cols.flatten())
    }

    @Test
    fun degenerate_sizes_give_nothing() {
        val items = listOf(event("a"))
        assertTrue(flowColumns(items, 0, 4).isEmpty())
        assertTrue(flowColumns(items, -1, 4).isEmpty())
        assertTrue(flowColumns(items, 3, 0).isEmpty())
    }

    @Test
    fun the_input_is_not_aliased() {
        val items = mutableListOf(event("a"), event("b"))
        val cols = flowColumns(items, 5, 1)
        items.clear()
        assertEquals(2, cols.single().size)
    }

    @Test
    fun any_list_flows_in_order_with_no_column_over_capacity_and_no_orphaned_header() {
        val rnd = Random(42)
        repeat(300) {
            val items = List(rnd.nextInt(30)) { if (rnd.nextInt(4) == 0) day("D$it") else event("e$it") }
            val rows = 1 + rnd.nextInt(8)
            val cols = 1 + rnd.nextInt(5)
            val out = flowColumns(items, rows, cols)
            assertTrue(out.size <= cols)
            for (c in out) {
                assertTrue("a column is never empty", c.isNotEmpty())
                assertTrue("a column holds at most $rows", c.size <= rows)
                assertTrue("a column never ends in a header: ${titles(out)}", c.last().kind != "header")
            }
            // Order is preserved: what comes out is a subsequence of the input, and only headers are ever skipped.
            val flat = out.flatten()
            var at = 0
            for (item in flat) {
                while (at < items.size && items[at] !== item) {
                    assertEquals("only headers may be skipped", "header", items[at].kind)
                    at++
                }
                assertTrue(at < items.size)
                at++
            }
        }
    }

    @Test
    fun agenda_grid_balances_a_short_calendar_over_two_wide_columns() {
        // 18 calendar rows where 19 fit in one column: two columns of 10, not one narrow column.
        assertEquals(2 to 10, io.haku.tablet.ui.detail.agendaGrid(18, 19, minColumns = 2))
        // Activity always uses four, as many rows as fit.
        assertEquals(4 to 9, io.haku.tablet.ui.detail.agendaGrid(50, 9, minColumns = 4))
        // A long calendar takes as many columns as it needs, up to four.
        assertEquals(3 to 11, io.haku.tablet.ui.detail.agendaGrid(30, 12, minColumns = 2))
        assertEquals(4 to 5, io.haku.tablet.ui.detail.agendaGrid(90, 5, minColumns = 2))
        assertEquals(0 to 0, io.haku.tablet.ui.detail.agendaGrid(0, 10, minColumns = 2))
        assertEquals(0 to 0, io.haku.tablet.ui.detail.agendaGrid(10, 0, minColumns = 2))
    }
}
