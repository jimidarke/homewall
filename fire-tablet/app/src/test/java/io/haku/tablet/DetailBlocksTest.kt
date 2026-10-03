package io.haku.tablet

import io.haku.tablet.data.Detail
import io.haku.tablet.data.DetailBlock
import io.haku.tablet.data.RowItem
import io.haku.tablet.data.StatItem
import io.haku.tablet.ui.detail.BodyLayout
import io.haku.tablet.ui.detail.NOW_DP
import io.haku.tablet.ui.detail.OUTLOOK_ROW_DP
import io.haku.tablet.ui.detail.ROW_DP
import io.haku.tablet.ui.detail.ROW_WITH_SUB_DP
import io.haku.tablet.ui.detail.bodyLayout
import io.haku.tablet.ui.detail.detailBodyDp
import io.haku.tablet.ui.detail.factsHeightDp
import io.haku.tablet.ui.detail.groupBlocks
import io.haku.tablet.ui.detail.hiLo
import io.haku.tablet.ui.detail.detailRect
import io.haku.tablet.ui.detail.rowHeightDp
import io.haku.tablet.ui.detail.visibleRows
import io.haku.tablet.ui.GAP_DP
import io.haku.tablet.ui.GridArea
import io.haku.tablet.ui.HEADER_DP
import io.haku.tablet.ui.MARGIN_DP
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DetailBlocksTest {
    private fun row(label: String, sub: String? = null) = RowItem(null, null, label, "v", sub)
    private fun rows(title: String) = DetailBlock.Rows(title, listOf(row("a")))
    private val stats = DetailBlock.Stats(listOf(StatItem("a", "b")))

    @Test
    fun a_row_with_a_sub_takes_a_second_line() {
        assertEquals(ROW_DP, rowHeightDp(row("a")), 0f)
        assertEquals(ROW_WITH_SUB_DP, rowHeightDp(row("a", "sub")), 0f)
    }

    @Test
    fun only_whole_rows_are_shown() {
        val items = List(20) { row("r$it") }
        assertEquals(6, visibleRows(items, 6 * ROW_DP))
        assertEquals(5, visibleRows(items, 6 * ROW_DP - 1f))
        assertEquals(0, visibleRows(items, ROW_DP - 1f))
        assertEquals(3, visibleRows(items.take(3), 1000f))
        assertEquals(0, visibleRows(emptyList(), 1000f))
        assertEquals("px rounding does not cost a row", 6, visibleRows(items, 6 * ROW_DP - 0.005f))
    }

    @Test
    fun rows_with_subs_count_at_their_own_height() {
        val items = listOf(row("a"), row("b", "s"), row("c", "s"), row("d"))
        assertEquals(3, visibleRows(items, ROW_DP + 2 * ROW_WITH_SUB_DP))
        assertEquals(2, visibleRows(items, ROW_DP + 2 * ROW_WITH_SUB_DP - 1f))
        assertEquals(4, visibleRows(items, 2 * ROW_DP + 2 * ROW_WITH_SUB_DP))
    }

    @Test
    fun an_infinite_height_shows_every_row() {
        assertEquals(5, visibleRows(List(5) { row("r") }, Float.POSITIVE_INFINITY))
    }

    @Test
    fun hi_lo_shows_whichever_exists() {
        assertEquals("12° / 4°", hiLo("12°", "4°"))
        assertEquals("12°", hiLo("12°", null))
        assertEquals("4°", hiLo(null, "4°"))
        assertNull(hiLo(null, null))
    }

    @Test
    fun consecutive_rows_blocks_share_a_group_up_to_three() {
        val a = rows("a"); val b = rows("b"); val c = rows("c"); val d = rows("d")
        assertEquals(listOf(listOf(a, b, c), listOf(d)), groupBlocks(listOf(a, b, c, d)))
    }

    @Test
    fun other_blocks_are_groups_of_one_and_split_rows_runs() {
        val a = rows("a"); val b = rows("b")
        assertEquals(
            listOf(listOf(stats), listOf(a, b), listOf(stats), listOf(a)),
            groupBlocks(listOf(stats, a, b, stats, a)),
        )
        assertEquals(emptyList<List<DetailBlock>>(), groupBlocks(emptyList()))
    }

    // ---- the two-column weather layout ----

    private val chart = DetailBlock.Chart(null, 0L, 3600L, 49, emptyList(), emptyList(), null, "No history yet")
    private fun detail(blocks: List<DetailBlock>, right: List<DetailBlock> = emptyList()) =
        Detail(1, "x", "X", 0L, null, blocks, right)

    @Test
    fun two_columns_only_when_both_have_blocks() {
        assertEquals(BodyLayout.Two(listOf(stats), listOf(chart)), bodyLayout(detail(listOf(stats), listOf(chart))))
    }

    @Test
    fun one_populated_side_stacks_as_before() {
        assertEquals(BodyLayout.Single(listOf(stats)), bodyLayout(detail(listOf(stats))))
        assertEquals("a payload with no left column is not a lone right column", BodyLayout.Single(listOf(chart)),
            bodyLayout(detail(emptyList(), listOf(chart))))
        assertEquals(BodyLayout.Single(emptyList()), bodyLayout(detail(emptyList())))
    }

    @Test
    fun the_left_column_fits_six_facts_between_the_hero_and_three_outlook_days() {
        val area = GridArea(1024f, 600f, MARGIN_DP, HEADER_DP, MARGIN_DP, MARGIN_DP, GAP_DP)
        val body = detailBodyDp(detailRect(area).h)
        assertEquals("panel 532 minus padding 30, header 48 and its 8 gap", 446f, body, 0f)
        val facts = List(6) { row("f$it") }
        assertEquals(6, visibleRows(facts, factsHeightDp(body, outlookDays = 3)))
    }

    @Test
    fun a_taller_outlook_or_hero_costs_fact_rows_rather_than_overflowing() {
        assertEquals(446f - NOW_DP - 3 * OUTLOOK_ROW_DP - 32f, factsHeightDp(446f, 3), 0f)
        assertEquals(4, visibleRows(List(6) { row("f$it") }, factsHeightDp(446f, 5)))
        assertEquals(0, visibleRows(List(6) { row("f$it") }, factsHeightDp(100f, 3)))
    }
}
