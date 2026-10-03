package io.haku.tablet

import androidx.compose.runtime.MonotonicFrameClock
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.ImageBitmapConfig
import androidx.compose.ui.graphics.colorspace.ColorSpace
import androidx.compose.ui.graphics.colorspace.ColorSpaces
import io.haku.tablet.ui.backdrop.BackdropState
import io.haku.tablet.ui.backdrop.Photo
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class BackdropStateTest {
    /** A 60 Hz frame clock on virtual time, standing in for the Choreographer that drives `Animatable`. */
    private class FrameClock(private val scheduler: TestCoroutineScheduler) : MonotonicFrameClock {
        override suspend fun <R> withFrameNanos(onFrame: (frameTimeNanos: Long) -> R): R {
            delay(16)
            return onFrame(scheduler.currentTime * 1_000_000)
        }
    }

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

    private fun photo() = Photo(Pixel, Pixel, 0.4f)

    @Test
    fun newer_photo_keeps_the_back_photo_it_fades_over() = runTest {
        val s = BackdropState()
        val clock = FrameClock(testScheduler)
        val a = photo()
        val b = photo()
        val c = photo()
        launch(clock) { s.show(a) }
        advanceUntilIdle()
        assertSame(a, s.front)
        assertNull(s.back)

        launch(clock) { s.show(b) }
        advanceTimeBy(800)
        runCurrent()
        assertSame(b, s.front)
        assertSame(a, s.back)

        // c arrives mid-fade, and its show takes the fade over before the interrupted one has unwound.
        launch(clock) { s.show(c) }
        runCurrent()
        assertSame(c, s.front)
        assertSame("the interrupted fade must not drop the photo c fades in over", b, s.back)

        advanceUntilIdle()
        assertSame(c, s.front)
        assertNull("a finished fade drops its old photo", s.back)
        assertEquals(1f, s.fade.value)
    }

    @Test
    fun cancelled_fade_drops_its_back_photo() = runTest {
        val s = BackdropState()
        val clock = FrameClock(testScheduler)
        val a = photo()
        val b = photo()
        launch(clock) { s.show(a) }
        advanceUntilIdle()

        val job = launch(clock) { s.show(b) }
        advanceTimeBy(800)
        runCurrent()
        assertSame(a, s.back)
        job.cancel()   // the backdrop left composition mid-fade: nothing replaces it
        runCurrent()
        assertSame(b, s.front)
        assertNull(s.back)
    }
}
