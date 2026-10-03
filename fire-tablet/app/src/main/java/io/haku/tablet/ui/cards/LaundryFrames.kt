package io.haku.tablet.ui.cards

import androidx.compose.ui.graphics.Color
import io.haku.tablet.ui.theme.Haku
import kotlin.math.PI
import kotlin.math.sin

/*
 * The on-screen version of the esp-laundry LED bar (DESIGN 4.4): four segments, each a brightness 0..1, as a
 * pure function of the machine's mode, its `leds` and the time, so every frame is testable without a device.
 */

/** The pseudo-mode [ledStepMs] takes for a stale machine (whatever its mode, it sweeps the violet comet). */
internal const val LED_STALE = "stale"

internal const val LED_SEGMENTS = 4

private const val DONE_STEP_MS = 120L
private const val DONE_CALM_STEP_MS = 450L
private const val STALE_STEP_MS = 150L
private const val OVERTIME_STEP_MS = 100L
private const val BREATH_MS = 2_500.0

/** The bounce: out to the last segment and back, one segment per step. */
private val PingPong = intArrayOf(0, 1, 2, 3, 2, 1)

/**
 * How often an animated bar changes, or null when it is static (idle, running, or an unknown mode). Pass
 * [LED_STALE] for a stale machine. Every step is 100 ms or longer, so the bar never draws faster than 10 fps.
 */
fun ledStepMs(mode: String): Long? = when (mode) {
    "overtime" -> OVERTIME_STEP_MS
    "done" -> DONE_STEP_MS
    "done_calm" -> DONE_CALM_STEP_MS
    LED_STALE -> STALE_STEP_MS
    else -> null
}

/**
 * Whether a bar steps its clock. Only an animated mode (or a [machineStale] machine's comet) does, and
 * only while the card isn't [quiet]: the app offline, or the whole card stale. A quiet bar holds its
 * t = 0 frame, so data that may be minutes old never keeps the wall moving. A single machine HA has no
 * data for still sweeps on a live card, since "no data" there is news.
 */
fun ledAnimates(mode: String, machineStale: Boolean, quiet: Boolean): Boolean =
    !quiet && ledStepMs(if (machineStale) LED_STALE else mode) != null

/**
 * The four segment brightnesses at [tMillis] into the animation:
 * - idle: the first segment at 0.25;
 * - running: the first [leds] (clamped to 0..4) at full;
 * - overtime: the first segment breathing between 0.15 and 1 on a 2.5 s sine;
 * - done: one full segment bouncing 0-1-2-3-2-1 at 120 ms a step;
 * - done_calm: the same bounce at 450 ms a step, the head at 0.6 and a 0.2 trail where it just was;
 * - [stale], whatever the mode: a comet circling at 150 ms a step, its head at 1 with a 0.35 and 0.1 tail;
 * - any other mode: dark.
 */
fun ledFrame(mode: String, leds: Int, tMillis: Long, stale: Boolean): FloatArray {
    val f = FloatArray(LED_SEGMENTS)
    if (stale) {
        val head = Math.floorMod(tMillis / STALE_STEP_MS, LED_SEGMENTS.toLong()).toInt()
        f[head] = 1f
        f[(head + 3) % LED_SEGMENTS] = 0.35f
        f[(head + 2) % LED_SEGMENTS] = 0.1f
        return f
    }
    when (mode) {
        "idle" -> f[0] = 0.25f
        "running" -> f.fill(1f, 0, leds.coerceIn(0, LED_SEGMENTS))
        "overtime" -> f[0] = (0.15 + 0.85 * (0.5 + 0.5 * sin(2 * PI * tMillis / BREATH_MS))).toFloat()
        "done" -> f[PingPong[pingPongIndex(tMillis / DONE_STEP_MS)]] = 1f
        "done_calm" -> {
            val step = tMillis / DONE_CALM_STEP_MS
            // Trail first, so the head wins if they ever share a segment.
            if (step > 0) f[PingPong[pingPongIndex(step - 1)]] = 0.2f
            f[PingPong[pingPongIndex(step)]] = 0.6f
        }
    }
    return f
}

private fun pingPongIndex(step: Long): Int = Math.floorMod(step, PingPong.size.toLong()).toInt()

/** The bar's colour: violet while stale, the firmware's dim red while idle, else the machine's own colour. */
fun ledColorFor(mode: String, stale: Boolean, machineColor: Color): Color = when {
    stale -> Haku.ledStaleViolet
    mode == "idle" -> Haku.ledIdleRed
    else -> machineColor
}
