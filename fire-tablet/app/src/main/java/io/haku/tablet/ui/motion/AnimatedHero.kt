package io.haku.tablet.ui.motion

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ColorProducer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import io.haku.tablet.ui.text.FitText

/** Hero change (Contract 3.4): a 12 dp vertical slide and fade over 350 ms. */
private const val HERO_MS = 350
private val HeroSlide = 12.dp

/** What's left of a hero once its ticking numbers are gone: "1.2 kW" -> " kW", "Washer 34m left" -> "Washer m left". */
private fun skeleton(hero: String): String = hero.filterNot { it.isDigit() || it == '.' || it == ',' }

/**
 * Whether a hero change from [old] to [new] gets the slide: only when its shape changes, i.e. what's left
 * once digits, `.` and `,` are stripped ("Back open" -> "All closed", "Washer 1m left" -> "Washer done",
 * "—" -> "21°"). A number ticking inside the same shape ("1.1 kW" -> "1.2 kW", "57 L" -> "58 L") swaps in
 * place, so live readings that wobble between polls never set the wall moving while the house is quiet.
 */
fun heroChangeAnimates(old: String, new: String): Boolean = skeleton(old) != skeleton(new)

/**
 * A [FitText] hero. A change that [heroChangeAnimates] slides the new value up 12 dp into place as the old
 * one slides up and out, both fading, over 350 ms; any other change swaps the text in place, with no
 * transition. [color] is read while drawing, so a colour cross-fade never recomposes. Unclipped, so a
 * hero taller than its slot (see `slot`) is never cut during the move.
 */
@Composable
fun AnimatedHero(
    text: String,
    style: TextStyle,
    color: ColorProducer,
    minSize: TextUnit,
    modifier: Modifier = Modifier,
) {
    val slide = with(LocalDensity.current) { HeroSlide.roundToPx() }
    val versions = remember { HeroVersions(text) }
    AnimatedContent(
        targetState = versions.update(text),
        modifier = modifier,
        transitionSpec = {
            (slideInVertically(tween(HERO_MS)) { slide } + fadeIn(tween(HERO_MS))) togetherWith
                (slideOutVertically(tween(HERO_MS)) { -slide } + fadeOut(tween(HERO_MS))) using
                SizeTransform(clip = false)
        },
        contentAlignment = Alignment.BottomStart,
        label = "hero",
    ) { version ->
        FitText(versions.textOf(version), style = style, minSize = minSize, color = color, modifier = Modifier.fillMaxWidth())
    }
}

/** Versions kept for content still sliding out; anything older has long finished its 350 ms. */
private const val RETIRED_KEPT = 3

/**
 * The hero's text per `AnimatedContent` version. Only a change that [heroChangeAnimates] starts a new
 * version (and so a slide); any other change rewrites the current version's text in place. That text is
 * snapshot state read only by the shown content, so the swap recomposes just the text. Retired versions
 * keep the text they had, for their slide out. Updated from composition, like `rememberUpdatedState`.
 */
@Stable
private class HeroVersions(first: String) {
    private var version = 0
    private var latest = first   // plain mirror of [current]: compared in composition without subscribing to it
    private val current = mutableStateOf(first)
    private val retired = HashMap<Int, String>()

    /** Takes [text] as the newest hero and returns the version that shows it. */
    fun update(text: String): Int {
        if (text != latest) {
            if (heroChangeAnimates(latest, text)) {
                retired[version] = latest
                version++
                retired.keys.removeAll { it < version - RETIRED_KEPT }
            }
            latest = text
            current.value = text
        }
        return version
    }

    fun textOf(v: Int): String = if (v == version) current.value else retired[v] ?: current.value
}
