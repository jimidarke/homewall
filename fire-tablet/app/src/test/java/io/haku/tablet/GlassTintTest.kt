package io.haku.tablet

import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.ImageBitmapConfig
import androidx.compose.ui.graphics.colorspace.ColorSpace
import androidx.compose.ui.graphics.colorspace.ColorSpaces
import io.haku.tablet.ui.backdrop.Photo
import io.haku.tablet.ui.backdrop.fadedGlassTint
import io.haku.tablet.ui.backdrop.glassTint
import io.haku.tablet.ui.backdrop.scrimAlpha
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GlassTintTest {
    private val lumas = (0..100).map { it / 100f }

    private object Pixel : ImageBitmap {
        override val width = 1
        override val height = 1
        override val colorSpace: ColorSpace = ColorSpaces.Srgb
        override val hasAlpha = false
        override val config = ImageBitmapConfig.Argb8888
        override fun readPixels(
            buffer: IntArray, startX: Int, startY: Int, width: Int, height: Int, bufferOffset: Int, stride: Int,
        ) = Unit
        override fun prepareToDraw() = Unit
    }

    private fun photo(luma: Float) = Photo(Pixel, Pixel, luma)

    @Test
    fun ramps_from_dark_to_bright_photos() {
        assertEquals(0.32f, glassTint(0f), 1e-6f)
        assertEquals("the scrim's dark bound", 0.32f, glassTint(0.15f), 1e-6f)
        assertEquals(0.40f, glassTint(0.375f), 1e-6f)
        assertEquals("the scrim's bright bound", 0.48f, glassTint(0.60f), 1e-6f)
        assertEquals(0.48f, glassTint(1f), 1e-6f)
        lumas.zipWithNext().forEach { (a, b) -> assertTrue("$a..$b", glassTint(b) >= glassTint(a)) }
    }

    @Test
    fun no_photo_keeps_the_v2_tint() {
        assertEquals(0.55f, glassTint(null), 0f)
        // Darker than any photo's tint: with nothing to frost, the glass sits on the plain night gradient.
        for (l in lumas) assertTrue("luma $l", glassTint(l) < glassTint(null))
    }

    @Test
    fun out_of_range_and_unknown_lumas_stay_in_bounds() {
        assertEquals(0.32f, glassTint(-1f), 1e-6f)
        assertEquals(0.48f, glassTint(2f), 1e-6f)
        assertEquals("unknown gets the most, like the scrim", 0.48f, glassTint(Float.NaN), 1e-6f)
    }

    @Test
    fun ramps_over_the_same_lumas_as_the_scrim() {
        // Both are flat outside the same bounds and move together inside them.
        for (l in lumas) {
            val glass = (glassTint(l) - 0.32f) / (0.48f - 0.32f)
            val scrim = (scrimAlpha(l, top = true) - 0.40f) / (0.75f - 0.40f)
            assertEquals("luma $l", scrim, glass, 1e-5f)
        }
    }

    @Test
    fun cross_fades_with_the_backdrop() {
        val dark = photo(0.1f)
        val bright = photo(0.9f)
        // Idle: the front photo's tint; the back slot is empty and the fade is done.
        assertEquals(0.32f, fadedGlassTint(dark, null, 1f), 1e-6f)
        // Photo to photo: from the old one's tint to the new one's.
        assertEquals(0.32f, fadedGlassTint(bright, dark, 0f), 1e-6f)
        assertEquals(0.40f, fadedGlassTint(bright, dark, 0.5f), 1e-6f)
        assertEquals(0.48f, fadedGlassTint(bright, dark, 1f), 1e-6f)
        // The first photo fades in from the no-photo tint, and night fades back out to it.
        assertEquals(0.55f, fadedGlassTint(dark, null, 0f), 1e-6f)
        assertEquals(0.55f, fadedGlassTint(null, bright, 1f), 1e-6f)
        assertEquals(0.515f, fadedGlassTint(null, bright, 0.5f), 1e-6f)
        // Nothing at all.
        assertEquals(0.55f, fadedGlassTint(null, null, 0.3f), 0f)
    }
}
