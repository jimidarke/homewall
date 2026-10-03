package io.haku.tablet.ui

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import java.time.Instant
import java.time.ZoneId

private val HM = Regex("""(\d{1,2}):(\d{2})""")
private const val MINUTE_MS = 60_000L
private const val MIN_BRIGHTNESS = 0.01f

/** "22:00" -> 1320 (minutes since midnight); "7:05" -> 425. Anything that isn't a valid 0:00..23:59 clock time is null. */
fun parseHm(s: String): Int? {
    val m = HM.matchEntire(s.trim()) ?: return null
    val h = m.groupValues[1].toInt()
    val min = m.groupValues[2].toInt()
    return if (h in 0..23 && min in 0..59) h * 60 + min else null
}

/**
 * Whether [minuteOfDay] falls in the dim window [start, end): start inclusive, end exclusive,
 * wrapping midnight when end < start. A blank or invalid bound, or start == end, never dims.
 */
fun isNight(minuteOfDay: Int, start: String, end: String): Boolean {
    val s = parseHm(start) ?: return false
    val e = parseHm(end) ?: return false
    return when {
        s == e -> false
        s < e -> minuteOfDay in s until e
        else -> minuteOfDay >= s || minuteOfDay < e
    }
}

/** Minutes since local midnight at [epochMs]. The tablet's zone is the house's own, so this is the house's wall clock. */
fun minuteOfDay(epochMs: Long, zone: ZoneId = ZoneId.systemDefault()): Int {
    val t = Instant.ofEpochMilli(epochMs).atZone(zone).toLocalTime()
    return t.hour * 60 + t.minute
}

/** The sidecar config isn't range-checked, and a 0 brightness would black the screen out. */
fun clampBrightness(b: Float): Float = b.coerceIn(MIN_BRIGHTNESS, 1f)

/**
 * Emits the current time now, then once per minute boundary. Wall-clock based, so it re-syncs
 * if the clock jumps; it never ticks faster than the boundary (an early wake just re-waits).
 */
fun minuteTicks(clock: () -> Long = System::currentTimeMillis): Flow<Long> = flow {
    while (true) {
        val now = clock()
        emit(now)
        delay(MINUTE_MS - now % MINUTE_MS)
    }
}
