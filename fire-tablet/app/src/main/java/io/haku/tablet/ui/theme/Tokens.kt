package io.haku.tablet.ui.theme

import androidx.compose.animation.core.SpringSpec
import androidx.compose.animation.core.spring
import androidx.compose.ui.graphics.Color

/** HAku tablet design tokens (Contract 3.1 and 3.4). */
object Haku {
    val ink = Color(0xFFFAF6EE)
    // 0.72 in v2; raised with v3's lighter glass so 16 sp muted text keeps 7:1 on bright photos (DESIGN §8.3).
    val inkMuted = ink.copy(alpha = 0.78f)
    val inkFaint = ink.copy(alpha = 0.48f)
    val night = Color(0xFF0C1211)
    val sage = Color(0xFF5B8C7F)
    val coral = Color(0xFFD4673E)
    val amber = Color(0xFFD9A441)
    val offline = Color(0xFF6E7471)

    val water = Color(0xFF4FB3E8)
    val heat = Color(0xFFF2994A)
    val cool = Color(0xFF7CCBF2)
    val washer = Color(0xFF00AAFF)
    val dryer = Color(0xFFFF6900)
    val ledIdleRed = Color(0xFFE5484D)
    val ledStaleViolet = Color(0xFF9B7BEA)

    /** Colour and alpha changes: critically damped, no overshoot. */
    fun <T> effectsSlow(): SpringSpec<T> = spring(dampingRatio = 1f, stiffness = 800f)

    /** Position and size changes: a touch of settle. */
    fun <T> spatialStandard(): SpringSpec<T> = spring(dampingRatio = 0.9f, stiffness = 700f)
}

/**
 * Parses `#RRGGBB`, `#AARRGGBB` and the Roku's `0xRRGGBBAA` (case-insensitive). Anything else, including
 * whitespace and sign characters that `toLong(16)` would otherwise tolerate, returns [fallback].
 */
fun parseColor(s: String, fallback: Color = Haku.sage): Color {
    val argb: Long = when {
        s.startsWith("#") -> when (s.length) {
            7 -> hex(s, 1)?.let { 0xFF000000L or it }
            9 -> hex(s, 1)
            else -> null
        }
        s.startsWith("0x", ignoreCase = true) && s.length == 10 ->
            hex(s, 2)?.let { ((it and 0xFFL) shl 24) or (it ushr 8) }   // RRGGBBAA -> AARRGGBB
        else -> null
    } ?: return fallback
    return Color(argb.toInt())
}

private fun hex(s: String, from: Int): Long? {
    val digits = s.substring(from)
    return if (digits.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) digits.toLong(16) else null
}

/** Card accent for a tile's glyph (Contract 3.1). */
fun accentFor(glyph: String): Color = when (glyph) {
    "door-open" -> Haku.amber
    "water" -> Haku.water
    "fire" -> Haku.heat
    "snowflake" -> Haku.cool
    "fan" -> Haku.sage
    "washing-machine" -> Haku.washer
    "tumble-dryer" -> Haku.dryer
    else -> Haku.sage
}

/** Agenda row accent for an item's glyph (Contract 3.1). Calendar rows use `parseColor(dot)` instead. */
fun itemAccent(glyph: String): Color = when (glyph) {
    "door-open", "lock-open-variant" -> Haku.amber
    "home-account" -> Haku.sage
    else -> Haku.inkMuted
}
