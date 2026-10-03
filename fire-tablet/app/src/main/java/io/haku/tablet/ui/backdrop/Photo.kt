package io.haku.tablet.ui.backdrop

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import io.haku.tablet.ui.HEADER_DP

/**
 * One backdrop photo: the full-screen [sharp] image, the small pre-blurred [soft] copy the cards frost
 * from, and the [luma] that sets the scrim. Identity equality on purpose: every load is a new photo, even
 * of the same file, so the backdrop always cross-fades to it.
 */
class Photo(val sharp: ImageBitmap, val soft: ImageBitmap, val luma: Float)

/** Turns image bytes into bitmaps. Returns null for anything it can't decode (including an empty body). */
interface PhotoDecoder {
    fun sharp(bytes: ByteArray): ImageBitmap?

    /** The bitmap and its [meanLuma]. */
    fun soft(bytes: ByteArray): Pair<ImageBitmap, Float>?
}

/** Screen height the header band is measured against (the 1024x600 design). */
private const val SCREEN_DP = 600

/**
 * [BitmapFactory] decoding. The sharp photo goes straight to a GPU-only HARDWARE bitmap (no Java-heap copy),
 * falling back to ARGB_8888 (never RGB_565, which bands the sky). The soft one stays a software ARGB_8888
 * bitmap so its pixels can be read for the luma. No `recycle()`: dropped bitmaps are left to the GC.
 */
class AndroidPhotoDecoder : PhotoDecoder {
    override fun sharp(bytes: ByteArray): ImageBitmap? {
        if (bytes.isEmpty()) return null
        val hardware = try {
            decode(bytes, Bitmap.Config.HARDWARE)
        } catch (e: IllegalArgumentException) {   // no hardware bitmap for this image or device
            null
        }
        val bitmap = hardware ?: decode(bytes, Bitmap.Config.ARGB_8888)?.also { it.prepareToDraw() } ?: return null
        return bitmap.asImageBitmap()
    }

    override fun soft(bytes: ByteArray): Pair<ImageBitmap, Float>? {
        if (bytes.isEmpty()) return null
        val bitmap = decode(bytes, Bitmap.Config.ARGB_8888) ?: return null
        val w = bitmap.width
        val h = bitmap.height
        val px = IntArray(w * h)
        bitmap.getPixels(px, 0, w, 0, 0, w, h)
        val luma = meanLuma(px, w, topRows = (h * HEADER_DP / SCREEN_DP).toInt().coerceAtLeast(1))
        bitmap.prepareToDraw()
        return bitmap.asImageBitmap() to luma
    }

    private fun decode(bytes: ByteArray, config: Bitmap.Config): Bitmap? {
        val options = BitmapFactory.Options().apply { inPreferredConfig = config }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
    }
}
