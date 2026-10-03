package io.haku.tablet.ui.motion

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue

/** Ring pulse (Contract 3.4): 1,400 ms each, FastOutSlowIn. */
private const val RING_MS = 1400

/**
 * A card's one-shot ring: 0 at rest; when [seq] changes, it runs [count] rings, each 0 → 1 over 1.4 s, then
 * rests at 0 again. Draw a ring only while the value is strictly between 0 and 1.
 *
 * The baseline is [seq] at first composition, so a card composed mid-run (a restarted activity, a config
 * reload) never replays an old pulse. Read the value only in a draw lambda.
 */
@Composable
fun rememberPulse(seq: Int, count: Int): State<Float> {
    val ring = remember { Animatable(0f) }
    var seen by remember { mutableIntStateOf(seq) }
    LaunchedEffect(seq) {
        if (seq == seen) return@LaunchedEffect
        seen = seq
        repeat(count) {
            ring.snapTo(0f)
            ring.animateTo(1f, tween(RING_MS, easing = FastOutSlowInEasing))
        }
        ring.snapTo(0f)
    }
    return ring.asState()
}
