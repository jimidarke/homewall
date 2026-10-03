package io.haku.tablet.ui.cards

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import io.haku.tablet.ui.backdrop.BackdropState
import io.haku.tablet.ui.backdrop.fadedGlassTint
import io.haku.tablet.ui.backdrop.glassTint
import io.haku.tablet.ui.theme.Haku

/** The glass's resting rim (ink at 8%) and the light along its top edge (ink at 12%, fading out). */
private val Hairline = 1.dp
private const val RIM_ALPHA = 0.08f
private const val HIGHLIGHT_ALPHA = 0.12f

/**
 * Smoked glass (Contract 3.2) for any surface over the backdrop: clipped to a [radius] round rect, the photo
 * behind it frosted ([frost], placed by [origin]), a `night` tint over that, then the surface's own drawing,
 * under a 1 dp ink rim and a 1 dp top highlight that follows the corners and is gone by the end of the curve.
 * No shadows: they would show through.
 *
 * The tint follows the photo ([fadedGlassTint]): lighter on dark photos, darker on bright ones, 0.55 with no
 * photo or no [backdrop]. It and the cross-fade it follows are read in the draw phase only, so a new photo
 * redraws the glass without recomposing anything. Move the surface with layout, as [frost] requires.
 *
 * [GlassCard] adds its lit and alert rim, glow and pulse inside this, under the resting rim and highlight.
 */
fun Modifier.glass(backdrop: BackdropState?, origin: FrostOrigin, radius: Dp): Modifier =
    this
        .clip(RoundedCornerShape(radius))
        .frost(backdrop, origin, radius)
        .drawWithCache {
            val corner = radius.toPx()
            val hairline = Hairline.toPx()
            val edgeTopLeft = Offset(hairline / 2, hairline / 2)
            val edgeSize = Size(size.width - hairline, size.height - hairline)
            val edgeCorner = CornerRadius(corner - hairline / 2)
            val edgeStroke = Stroke(hairline)
            val rim = Haku.ink.copy(alpha = RIM_ALPHA)
            val highlight = Brush.verticalGradient(
                0f to Haku.ink.copy(alpha = HIGHLIGHT_ALPHA),
                1f to Haku.ink.copy(alpha = 0f),
                startY = 0f,
                endY = corner,
            )
            onDrawWithContent {
                val tint = backdrop?.let { fadedGlassTint(it.front, it.back, it.fade.value) } ?: glassTint(null)
                drawRect(Haku.night.copy(alpha = tint))
                drawContent()
                drawRoundRect(rim, edgeTopLeft, edgeSize, edgeCorner, style = edgeStroke)
                drawRoundRect(highlight, edgeTopLeft, edgeSize, edgeCorner, style = edgeStroke)
            }
        }
