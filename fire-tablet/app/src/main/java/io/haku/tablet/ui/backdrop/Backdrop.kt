package io.haku.tablet.ui.backdrop

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.util.lerp
import io.haku.tablet.ui.theme.Haku
import kotlin.math.roundToInt

/**
 * The full-screen layer behind everything: night with a soft sage light from the top left (plain solid
 * night while [night]), the photo cross-fading over it, and a `night` scrim that deepens toward the header
 * on bright photos, lifted while the photo peek runs ([BackdropState.veil]). One draw node; the photos, the
 * fade and the veil are read in the draw phase, so neither a cross-fade nor a peek recomposes.
 */
@Composable
fun Backdrop(photo: Photo?, state: BackdropState, night: Boolean, modifier: Modifier = Modifier) {
    LaunchedEffect(photo) { state.show(photo) }
    Spacer(
        modifier
            .fillMaxSize()
            .onSizeChanged { state.rootSize = it }
            .drawWithCache {
                val light = if (night) {
                    null
                } else {
                    Brush.radialGradient(
                        colors = listOf(Haku.sage.copy(alpha = 0.35f), Haku.night),
                        center = Offset(size.width * 0.2f, 0f),
                        radius = size.maxDimension,
                    )
                }
                val dst = IntSize(size.width.roundToInt(), size.height.roundToInt())
                onDrawBehind {
                    val p = state.fade.value
                    val front = state.front
                    val back = state.back
                    // An opaque photo at full alpha hides the gradient: skip the fill.
                    val covered = front != null && (back != null || p >= 1f)
                    if (!covered) {
                        drawRect(Haku.night)
                        light?.let { drawRect(it) }
                    }
                    back?.let { drawSharp(it, dst, backAlpha(front, p)) }
                    front?.let { drawSharp(it, dst, p) }
                    drawScrim(front, back, p, rootHeight = size.height, strength = 1f - state.veil.value)
                }
            },
    )
}

private fun DrawScope.drawSharp(photo: Photo, dst: IntSize, alpha: Float) =
    drawImage(photo.sharp, dstSize = dst, alpha = alpha, filterQuality = FilterQuality.Low)

/**
 * The `night` scrim over the photos: a vertical gradient over the root's height, from [scrimAlpha] at the
 * top to its bottom value, shifted up by [top] (the element's top in the root) so an element draws exactly
 * its slice of it. It fades in and out with a lone photo, so the gradient never jumps, and cross-fades its
 * strength between two. With no photo it draws nothing. [strength] scales it all, down to nothing while the
 * photo peek shows the bare photo (1 - [BackdropState.veil]).
 */
internal fun DrawScope.drawScrim(
    front: Photo?,
    back: Photo?,
    p: Float,
    rootHeight: Float,
    top: Float = 0f,
    strength: Float = 1f,
) {
    if (strength <= 0f) return
    val shown = strength * when {
        front != null && back != null -> 1f
        front != null -> p
        back != null -> 1f - p
        else -> return
    }
    val luma = if (front != null && back != null) lerp(back.luma, front.luma, p) else (front ?: back ?: return).luma
    drawRect(
        Brush.verticalGradient(
            0f to Haku.night.copy(alpha = scrimAlpha(luma, top = true) * shown),
            1f to Haku.night.copy(alpha = scrimAlpha(luma, top = false) * shown),
            startY = -top,
            endY = rootHeight - top,
        ),
    )
}
