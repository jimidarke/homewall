package io.haku.tablet

import io.haku.tablet.data.TileSpec
import io.haku.tablet.ui.GAP_DP
import io.haku.tablet.ui.GridArea
import io.haku.tablet.ui.HEADER_DP
import io.haku.tablet.ui.MARGIN_DP
import io.haku.tablet.ui.TileRect
import io.haku.tablet.ui.detail.detailContentAlpha
import io.haku.tablet.ui.detail.detailRect
import io.haku.tablet.ui.detail.lerpRect
import io.haku.tablet.ui.tileRect
import org.junit.Assert.assertEquals
import org.junit.Test

class DetailRectTest {
    private val area = GridArea(1024f, 600f, MARGIN_DP, HEADER_DP, MARGIN_DP, MARGIN_DP, GAP_DP)

    @Test
    fun panel_fills_the_grid_area_below_the_header() {
        assertEquals(TileRect(12f, 56f, 1000f, 532f), detailRect(area))
    }

    @Test
    fun panel_covers_every_card_exactly() {
        val full = detailRect(area)
        val first = tileRect(4, 3, TileSpec(col = 0, row = 0), area)
        val last = tileRect(4, 3, TileSpec(col = 3, row = 2), area)
        assertEquals(full.x, first.x, 0.001f)
        assertEquals(full.y, first.y, 0.001f)
        assertEquals(full.x + full.w, last.x + last.w, 0.001f)
        assertEquals(full.y + full.h, last.y + last.h, 0.001f)
    }

    @Test
    fun reveal_grows_from_the_card_to_the_panel() {
        val from = TileRect(100f, 200f, 50f, 40f)
        val to = TileRect(0f, 0f, 1000f, 500f)
        assertEquals(from, lerpRect(from, to, 0f))
        assertEquals(to, lerpRect(from, to, 1f))
        assertEquals(TileRect(50f, 100f, 525f, 270f), lerpRect(from, to, 0.5f))
        assertEquals(to, lerpRect(from, to, 1.5f))
        assertEquals(from, lerpRect(from, to, -1f))
    }

    @Test
    fun content_fades_in_over_the_end_of_the_reveal() {
        assertEquals(0f, detailContentAlpha(0f), 0f)
        assertEquals(0f, detailContentAlpha(0.4f), 1e-6f)
        assertEquals(0.5f, detailContentAlpha(0.7f), 0.0001f)
        assertEquals(1f, detailContentAlpha(1f), 0f)
    }
}
