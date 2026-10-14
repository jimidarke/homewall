package io.haku.tablet.ui.backdrop

/**
 * Mean Rec. 709 luma of [argb] (row-major, [width] wide), 0..1: the larger of the whole frame and its top
 * [topRows] rows. The header clock sits on bare photo under the scrim, so a bright sky has to count even
 * when the rest of the frame is dark.
 */
fun meanLuma(argb: IntArray, width: Int, topRows: Int): Float {
    if (argb.isEmpty()) return 0f
    val topN = (topRows.coerceAtLeast(1) * width.coerceAtLeast(1)).coerceAtMost(argb.size)
    var all = 0.0
    var top = 0.0
    for (i in argb.indices) {
        val c = argb[i]
        val y = 0.2126 * ((c shr 16) and 0xFF) + 0.7152 * ((c shr 8) and 0xFF) + 0.0722 * (c and 0xFF)
        all += y
        if (i < topN) top += y
    }
    return (maxOf(all / argb.size, top / topN) / 255.0).toFloat()
}

/** Below this luma the scrim stays at its floor; above [BRIGHT] it is at its ceiling. */
private const val DARK = 0.15f
private const val BRIGHT = 0.60f

/** Scrim alpha at the top (header) and bottom of the screen, for the darkest and brightest photos. */
private const val TOP_MIN = 0.40f
private const val TOP_MAX = 0.75f
private const val BOTTOM_MIN = 0.25f
private const val BOTTOM_MAX = 0.40f

/** The glass card's `night` tint over its frost, for the darkest and brightest photos (v3 contract §3). */
private const val GLASS_MIN = 0.32f
private const val GLASS_MAX = 0.48f

/** The tint with no photo behind the glass (backgrounds off, no photos, no config yet): v2's smoked glass. */
private const val GLASS_NO_PHOTO = 0.55f

/** Where [luma] sits between [DARK] (0) and [BRIGHT] (1), clamped. An unknown (NaN) luma counts as bright. */
private fun brightness(luma: Float): Float =
    if (luma.isNaN()) 1f else ((luma - DARK) / (BRIGHT - DARK)).coerceIn(0f, 1f)

/**
 * Alpha of the `night` scrim over a photo of [luma] (from [meanLuma]), at the [top] or bottom edge of a
 * vertical gradient. Brighter photos get more scrim, the top more than the bottom, so the header clock and
 * date stay legible on a sunny sky while a dark photo still reads through. Range 0.25..0.75; an unknown
 * (NaN) luma gets the most.
 */
fun scrimAlpha(luma: Float, top: Boolean): Float {
    val t = brightness(luma)
    return if (top) TOP_MIN + (TOP_MAX - TOP_MIN) * t else BOTTOM_MIN + (BOTTOM_MAX - BOTTOM_MIN) * t
}

/**
 * Alpha of the `night` tint a glass card lays over its frost, for a photo of [luma] (from [meanLuma]), or
 * null for no photo. It ramps like [scrimAlpha], over the same luma bounds, from 0.32 on dark photos to
 * 0.48 on bright ones: the frost already carries its slice of the scrim, so the glass can stay light where
 * the photo is dark and still hold small text at 7:1 on a bright one. An unknown (NaN) luma gets the most.
 * With no photo the glass sits on the plain `night` gradient and keeps v2's 0.55.
 */
fun glassTint(luma: Float?): Float =
    if (luma == null) GLASS_NO_PHOTO else GLASS_MIN + (GLASS_MAX - GLASS_MIN) * brightness(luma)

/**
 * [glassTint] through the backdrop's cross-fade from [back] to [front] at [p] (0 = all back, 1 = all front),
 * so the glass lightens or darkens with the photo the way the scrim does. A null side is no photo: fading
 * in the first photo, or out to night, ramps from or to the no-photo tint.
 */
fun fadedGlassTint(front: Photo?, back: Photo?, p: Float): Float {
    val from = glassTint(back?.luma)
    return from + (glassTint(front?.luma) - from) * p.coerceIn(0f, 1f)
}
