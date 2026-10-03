package io.haku.tablet.ui

import io.haku.tablet.data.TileSpec
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.transformLatest

data class TileRect(val x: Float, val y: Float, val w: Float, val h: Float)

/** The grid's box in root coordinates: its full [width] x [height], the edge insets, and the [gap] between cells. */
data class GridArea(
    val width: Float, val height: Float,
    val left: Float, val top: Float, val right: Float, val bottom: Float,
    val gap: Float,
)

const val HEADER_DP = 56f
const val MARGIN_DP = 12f
const val GAP_DP = 10f

/**
 * Place [tile] on a cols x rows grid inside [area]: cells are inset by the area's edges and
 * separated by its gap. Spans past the grid edge are clamped. The result is in root coordinates.
 */
fun tileRect(cols: Int, rows: Int, tile: TileSpec, area: GridArea): TileRect {
    val c = cols.coerceAtLeast(1)
    val r = rows.coerceAtLeast(1)
    val col = tile.col.coerceIn(0, c - 1)
    val row = tile.row.coerceIn(0, r - 1)
    val spanW = tile.w.coerceIn(1, c - col)
    val spanH = tile.h.coerceIn(1, r - row)
    val cellW = (area.width - area.left - area.right - area.gap * (c - 1)) / c
    val cellH = (area.height - area.top - area.bottom - area.gap * (r - 1)) / r
    return TileRect(
        x = area.left + col * (cellW + area.gap),
        y = area.top + row * (cellH + area.gap),
        w = cellW * spanW + area.gap * (spanW - 1),
        h = cellH * spanH + area.gap * (spanH - 1),
    )
}

enum class Freshness { LIVE, LAGGING, OFFLINE }

/**
 * Whether the app shows itself offline (banner, dimmed and quieted cards): [fresh] is OFFLINE and a state
 * fetch has completed. Freshness starts OFFLINE before the first poll, and a cold start must not flash
 * "No data" only to slide it away a moment later.
 */
fun offlineShown(fresh: Freshness, stateFetched: Boolean): Boolean = stateFetched && fresh == Freshness.OFFLINE

const val LAGGING_AFTER_MS = 30_000L
const val OFFLINE_AFTER_MS = 120_000L

/** How fresh the last good /api/state is. Never fetched counts as offline. */
fun freshness(lastOkAtMs: Long?, nowMs: Long): Freshness {
    if (lastOkAtMs == null) return Freshness.OFFLINE
    val age = nowMs - lastOkAtMs
    return when {
        age <= LAGGING_AFTER_MS -> Freshness.LIVE
        age <= OFFLINE_AFTER_MS -> Freshness.LAGGING
        else -> Freshness.OFFLINE
    }
}

/**
 * [freshness] over time, with no polling: each good poll emits its state, then the flow sleeps
 * until the instant the age crosses the next boundary and re-evaluates there, stopping at
 * OFFLINE. A newer poll cancels the sleep and starts over. Emits only when the state changes.
 */
@OptIn(ExperimentalCoroutinesApi::class)
fun freshnessFlow(lastOkAt: Flow<Long?>, clock: () -> Long = System::currentTimeMillis): Flow<Freshness> =
    lastOkAt.transformLatest { t ->
        if (t == null) {
            emit(Freshness.OFFLINE)
            return@transformLatest
        }
        while (true) {
            val now = clock()
            val f = freshness(t, now)
            emit(f)
            // Age must be strictly past a boundary to flip, so the next look is 1 ms after it.
            val flipsAt = when (f) {
                Freshness.LIVE -> t + LAGGING_AFTER_MS + 1
                Freshness.LAGGING -> t + OFFLINE_AFTER_MS + 1
                Freshness.OFFLINE -> return@transformLatest
            }
            delay(flipsAt - now)
        }
    }.distinctUntilChanged()
