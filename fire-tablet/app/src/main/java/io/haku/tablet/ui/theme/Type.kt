package io.haku.tablet.ui.theme

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.sp
import io.haku.tablet.R

/** Barlow (OFL), the only faces the app ships (Contract 3.3): Medium for text; Semi Condensed SemiBold for the clock, heroes and state words. */
private val Barlow = FontFamily(Font(R.font.barlow_medium, FontWeight.Medium))
private val BarlowSemiCondensed = FontFamily(Font(R.font.barlow_semi_condensed_semibold, FontWeight.SemiBold))

/**
 * Type scale (Contract 3.3). Nothing is below 16 sp. Every style that can show digits sets `tnum`, so a
 * ticking number does not make its neighbours jitter. Colour is applied at the call site, except the card
 * title, which is always muted.
 */
object HakuType {
    private const val TNUM = "tnum"

    val clock = TextStyle(
        fontFamily = BarlowSemiCondensed, fontWeight = FontWeight.SemiBold, fontSize = 40.sp, fontFeatureSettings = TNUM,
    )
    val date = TextStyle(
        fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 20.sp, fontFeatureSettings = TNUM,
    )

    /**
     * Fixed line height, trimmed both ends. The trim follows the font size, so a hero shrunk by `FitText`
     * measures shorter: cards give it a fixed slot rather than relying on this to hold the layout.
     */
    val hero = TextStyle(
        fontFamily = BarlowSemiCondensed, fontWeight = FontWeight.SemiBold, fontSize = 44.sp, fontFeatureSettings = TNUM,
        lineHeight = 44.sp,
        lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.Both),
    )

    /** Door state word, laundry status. */
    val state = TextStyle(
        fontFamily = BarlowSemiCondensed, fontWeight = FontWeight.SemiBold, fontSize = 26.sp, fontFeatureSettings = TNUM,
    )
    val sub = TextStyle(
        fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 20.sp, fontFeatureSettings = TNUM,
    )
    val agendaTitle = TextStyle(
        fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 18.sp, fontFeatureSettings = TNUM,
    )
    val detail = TextStyle(
        fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 16.sp, fontFeatureSettings = TNUM,
    )

    /** Sentence case as given by the sidecar; never upper-cased. */
    val cardTitle = TextStyle(
        fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 16.sp, color = Haku.inkMuted,
    )
}

/**
 * Pins `fontScale` to 1, so the system font-size setting cannot grow text out of its card. The wall tablet
 * is laid out in dp and sp that mean the same thing.
 */
@Composable
fun LockFontScale(content: @Composable () -> Unit) {
    val current = LocalDensity.current
    val locked = remember(current.density) { Density(current.density, fontScale = 1f) }
    CompositionLocalProvider(LocalDensity provides locked, content = content)
}
