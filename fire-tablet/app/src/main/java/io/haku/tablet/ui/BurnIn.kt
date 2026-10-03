package io.haku.tablet.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.produceState
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

/** Burn-in shift (Contract 3.4): one step every 10 min, no animation. */
private const val SHIFT_EVERY_MS = 10 * 60_000L

/** The 8 positions on a ±2 dp square ring, clockwise from the top left, so each step moves 2 dp on one axis. */
private val RING = listOf(
    IntOffset(-2, -2), IntOffset(0, -2), IntOffset(2, -2), IntOffset(2, 0),
    IntOffset(2, 2), IntOffset(0, 2), IntOffset(-2, 2), IntOffset(-2, 0),
)

/**
 * The burn-in shift at [epochMs], in **dp**: each 10-minute slot of the wall clock takes the next of the 8
 * positions on a ±2 dp ring, cycling. Pure; the caller converts to px ([toPx]).
 */
fun burnInOffset(epochMs: Long): IntOffset = RING[Math.floorMod(epochMs / SHIFT_EVERY_MS, RING.size.toLong()).toInt()]

/** A [burnInOffset] (in dp) in px. */
internal fun IntOffset.toPx(density: Density): IntOffset = with(density) { IntOffset(x.dp.roundToPx(), y.dp.roundToPx()) }

/**
 * The current [burnInOffset], stepping at each 10-minute boundary of the wall clock. Read it only in a
 * layout lambda (`Modifier.offset {}`), so a step re-places the UI without recomposing it.
 */
@Composable
fun rememberBurnInShift(clock: () -> Long = System::currentTimeMillis): State<IntOffset> =
    produceState(burnInOffset(clock())) {
        while (true) {
            val now = clock()
            value = burnInOffset(now)
            delay(SHIFT_EVERY_MS - now % SHIFT_EVERY_MS)
        }
    }
