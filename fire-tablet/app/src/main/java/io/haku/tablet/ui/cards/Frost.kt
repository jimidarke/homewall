package io.haku.tablet.ui.cards

import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.toRect
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.layout.onPlaced
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import io.haku.tablet.ui.backdrop.BackdropState
import io.haku.tablet.ui.backdrop.backAlpha
import io.haku.tablet.ui.backdrop.drawScrim
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.roundToInt

/** Where a card sits in the root, kept by [frost]'s `onPlaced`; read only in its draw lambda. */
@Stable
class FrostOrigin {
    var pos: Offset by mutableStateOf(Offset.Zero)
}

/**
 * Fake frosted glass for API 30 (no `RenderEffect`): draws this element's own region of the backdrop, blurred:
 * the pre-blurred soft photos, scaled up, under the same slice of the scrim the backdrop has there, all
 * clipped to a [radius] round rect. Cross-fades with the backdrop, and lifts its scrim with the peek's veil.
 * Without a backdrop, or with no photo, it draws nothing.
 *
 * The region comes from the element's position in the root, updated whenever it is (re)placed, so move
 * cards with layout (`Modifier.offset {}`), never a `graphicsLayer` translation, which skips `onPlaced`.
 */
fun Modifier.frost(bd: BackdropState?, origin: FrostOrigin, radius: Dp): Modifier =
    if (bd == null) {
        this
    } else {
        this
            .onPlaced { origin.pos = it.positionInRoot() }
            .drawWithCache {
                val clip = Path().apply { addRoundRect(RoundRect(size.toRect(), CornerRadius(radius.toPx()))) }
                val box = IntSize(size.width.roundToInt(), size.height.roundToInt())
                onDrawBehind {
                    val root = bd.rootSize
                    val front = bd.front
                    val back = bd.back
                    if (root.width == 0 || root.height == 0 || (front == null && back == null)) return@onDrawBehind
                    val p = bd.fade.value
                    val pos = origin.pos
                    clipPath(clip) {
                        back?.let { frostCrop(it.soft, pos, root, box, backAlpha(front, p)) }
                        front?.let { frostCrop(it.soft, pos, root, box, p) }
                        drawScrim(
                            front, back, p,
                            rootHeight = root.height.toFloat(),
                            top = pos.y,
                            strength = 1f - bd.veil.value,
                        )
                    }
                }
            }
    }

/**
 * Draws the part of [img] (the whole root, scaled down) that lies under an element at [pos] of size [size],
 * scaled back up. The source rect snaps outward to whole soft pixels (4 screen px each on the tablet), and
 * the destination shifts by the same rounding, so the crop lands where the photo is to within a screen
 * pixel; the caller's clip trims the overhang.
 */
private fun DrawScope.frostCrop(img: ImageBitmap, pos: Offset, root: IntSize, size: IntSize, alpha: Float) {
    val kx = img.width / root.width.toFloat()
    val ky = img.height / root.height.toFloat()
    val sx0 = floor(pos.x * kx).toInt().coerceIn(0, img.width - 1)
    val sy0 = floor(pos.y * ky).toInt().coerceIn(0, img.height - 1)
    val sx1 = ceil((pos.x + size.width) * kx).toInt().coerceIn(sx0 + 1, img.width)
    val sy1 = ceil((pos.y + size.height) * ky).toInt().coerceIn(sy0 + 1, img.height)
    val left = (sx0 / kx - pos.x).roundToInt()
    val top = (sy0 / ky - pos.y).roundToInt()
    val right = (sx1 / kx - pos.x).roundToInt()
    val bottom = (sy1 / ky - pos.y).roundToInt()
    drawImage(
        img,
        srcOffset = IntOffset(sx0, sy0),
        srcSize = IntSize(sx1 - sx0, sy1 - sy0),
        dstOffset = IntOffset(left, top),
        dstSize = IntSize(right - left, bottom - top),
        alpha = alpha,
        filterQuality = FilterQuality.Low,
    )
}
