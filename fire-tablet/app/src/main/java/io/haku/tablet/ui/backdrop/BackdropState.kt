package io.haku.tablet.ui.backdrop

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.AnimationVector1D
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.IntSize

/** Background cross-fade (Contract 3.4): 1.6 s, no zoom. */
private const val CROSS_FADE_MS = 1600

/**
 * The backdrop's two photo slots and the cross-fade between them, shared by the full-screen [Backdrop] and
 * every card's frost. Everything here is read in draw lambdas only, so a cross-fade redraws without
 * recomposing anything.
 */
@Stable
class BackdropState {
    /** The current photo, fading in while [fade] runs. Null is the plain gradient. */
    var front: Photo? by mutableStateOf(null)
        private set

    /** The photo fading out; null when idle, so the old pair can be collected. */
    var back: Photo? by mutableStateOf(null)
        private set

    /** 0 = all [back], 1 = all [front]. */
    val fade: Animatable<Float, AnimationVector1D> = Animatable(1f)

    /**
     * How far the photo peek has lifted the scrim: 0 = the scrim as usual, 1 = none, the bare photo. The
     * dashboard animates it; the backdrop's scrim and every frost's slice of it scale by 1 - veil ([drawScrim]).
     */
    val veil: Animatable<Float, AnimationVector1D> = Animatable(0f)

    /** The backdrop's size in root pixels: the frame the frost maps card positions against. */
    var rootSize: IntSize by mutableStateOf(IntSize.Zero)

    /**
     * Cross-fades to [next]. Run from one `LaunchedEffect(photo)`; a newer photo cancels it cleanly. The newer
     * show can take [back] over before this one has unwound, so this one drops only the photo it set there.
     */
    suspend fun show(next: Photo?) {
        if (next === front) return
        val prev = front
        back = prev
        front = next
        try {
            fade.snapTo(0f)
            fade.animateTo(1f, tween(CROSS_FADE_MS, easing = LinearOutSlowInEasing))
        } finally {
            if (back === prev) back = null   // drop the old pair; the GC frees it (no recycle())
        }
    }
}

val LocalBackdrop: ProvidableCompositionLocal<BackdropState?> = staticCompositionLocalOf { null }

/**
 * Alpha for [BackdropState.back] at fade [p]. Photos are opaque, so the back one stays at 1 and the front
 * fades in over it. Fading out to no photo (backgrounds off, an empty NAS) fades the back one out over the gradient.
 */
internal fun backAlpha(front: Photo?, p: Float): Float = if (front == null) 1f - p else 1f
