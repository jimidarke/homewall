package io.haku.tablet

import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.ImageBitmapConfig
import androidx.compose.ui.graphics.colorspace.ColorSpace
import androidx.compose.ui.graphics.colorspace.ColorSpaces
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import io.haku.tablet.data.Fetch
import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubJson
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.HubState
import io.haku.tablet.ui.DashboardViewModel
import io.haku.tablet.ui.PEEK_RETURN_MS
import io.haku.tablet.ui.backdrop.PhotoDecoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import java.util.TimeZone
import kotlin.coroutines.EmptyCoroutineContext

/**
 * The photo peek in the view model, on virtual time, with a NAS of one photo and a decoder that needs no
 * Android. The demo config dims from 22:00 UTC (the default zone is pinned to UTC here), and the wall clock
 * starts at 21:58, so night begins 2 minutes in.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PeekTest {
    private val scheduler = TestCoroutineScheduler()
    private val store = ViewModelStore()
    private val savedZone = TimeZone.getDefault()

    private val demoDir = File("src/debug/assets/demo")
    private val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
    private fun demo(name: String): HubState = HubJson.parseState(File(demoDir, "$name.json").readText())

    /** 21:58:00 UTC on some day. */
    private val start = 1_790_000_000_000L.let { it - it % 86_400_000L } + (21 * 60 + 58) * 60_000L

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

    private object PixelDecoder : PhotoDecoder {
        override fun sharp(bytes: ByteArray): ImageBitmap = Pixel
        override fun soft(bytes: ByteArray): Pair<ImageBitmap, Float> = Pixel to 0.4f
    }

    /** The demo house, quiet unless a test changes [state], with [photos] on the NAS. */
    private inner class FakeSource(private val photos: List<String>) : HubSource {
        var state: Fetch<HubState> = Fetch.Ok(demo("quiet"))
        override suspend fun config(): Fetch<HubConfig> = Fetch.Ok(this@PeekTest.config)
        override suspend fun state(): Fetch<HubState> = state
        override suspend fun backgrounds(): Fetch<List<String>> = Fetch.Ok(photos)
        override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> =
            Fetch.Ok(byteArrayOf(1))
    }

    @Before
    fun setUp() {
        TimeZone.setDefault(TimeZone.getTimeZone("UTC"))
        Dispatchers.setMain(StandardTestDispatcher(scheduler))
    }

    @After
    fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
        TimeZone.setDefault(savedZone)
    }

    private fun viewModel(source: HubSource): DashboardViewModel {
        val factory = viewModelFactory {
            initializer {
                DashboardViewModel(
                    source, "test",
                    clock = { start + scheduler.currentTime },
                    work = EmptyCoroutineContext,
                    decoder = PixelDecoder,
                )
            }
        }
        return ViewModelProvider(store, factory)[DashboardViewModel::class.java]
    }

    private fun advance(ms: Long) {
        scheduler.advanceTimeBy(ms)
        scheduler.runCurrent()
    }

    /** A view model with its first poll and its photo in. */
    private fun withPhoto(src: FakeSource = FakeSource(listOf("a.jpg"))): DashboardViewModel {
        val vm = viewModel(src)
        scheduler.runCurrent()
        assertNotNull("the photo loaded", vm.photo.value)
        return vm
    }

    @Test
    fun start_and_end() {
        val vm = withPhoto()
        assertFalse(vm.peek.value)
        vm.startPeek()
        assertTrue(vm.peek.value)
        vm.endPeek()
        assertFalse(vm.peek.value)
        vm.endPeek()   // ending twice is harmless
        assertFalse(vm.peek.value)
    }

    @Test
    fun returns_by_itself_after_30s() {
        val vm = withPhoto()
        vm.startPeek()
        advance(PEEK_RETURN_MS - 1)
        assertTrue(vm.peek.value)
        advance(1)
        assertFalse(vm.peek.value)
    }

    @Test
    fun an_ended_peek_cancels_its_return() {
        val vm = withPhoto()
        vm.startPeek()
        advance(10_000)
        vm.endPeek()
        advance(10_000)
        vm.startPeek()                       // a new peek at 20 s gets its own full 30 s
        advance(PEEK_RETURN_MS - 10_001)     // 39.999 s: past where the first peek's return would have been
        assertTrue(vm.peek.value)
        advance(10_001)                      // 50 s
        assertFalse(vm.peek.value)
    }

    @Test
    fun no_photo_no_peek() {
        val vm = viewModel(FakeSource(emptyList()))
        scheduler.runCurrent()
        assertNull(vm.photo.value)
        vm.startPeek()
        assertFalse(vm.peek.value)
    }

    @Test
    fun night_keeps_the_photo_and_the_peek() {
        val vm = withPhoto()
        advance(100_000)                     // 21:59:40
        assertFalse(vm.night.value)
        vm.startPeek()
        assertTrue(vm.peek.value)
        advance(20_000)                      // 22:00:00: night only dims the screen now
        assertTrue(vm.night.value)
        assertNotNull("photos rotate through the night", vm.photo.value)
        assertTrue("a peek in progress carries on", vm.peek.value)
        vm.endPeek()
        vm.startPeek()                       // and a new one starts at night
        assertTrue(vm.peek.value)
    }

    @Test
    fun an_alert_ends_the_peek() {
        val src = FakeSource(listOf("a.jpg"))
        val vm = withPhoto(src)
        vm.startPeek()
        src.state = Fetch.Ok(demo("busy"))
        advance(5_000)
        assertTrue("activity alone leaves the peek up", vm.peek.value)
        src.state = Fetch.Ok(demo("alert"))
        advance(5_000)
        assertFalse("an alert must never hide behind a peek", vm.peek.value)
    }

    @Test
    fun step_outside_a_peek_does_nothing() {
        val vm = withPhoto(FakeSource(listOf("a.jpg", "b.jpg")))
        val p = vm.photo.value
        vm.stepPhoto(+1)
        scheduler.runCurrent()
        assertSame(p, vm.photo.value)
    }

    @Test
    fun step_changes_the_photo_and_keeps_the_peek() {
        val vm = withPhoto(FakeSource(listOf("a.jpg", "b.jpg")))
        val p = vm.photo.value
        vm.startPeek()
        vm.stepPhoto(+1)
        scheduler.runCurrent()
        assertNotSame(p, vm.photo.value)
        assertTrue(vm.peek.value)
    }

    @Test
    fun a_step_restarts_the_return() {
        val vm = withPhoto(FakeSource(listOf("a.jpg", "b.jpg")))
        vm.startPeek()
        advance(20_000)
        vm.stepPhoto(+1)
        advance(PEEK_RETURN_MS - 1)          // 49.999 s
        assertTrue(vm.peek.value)
        advance(1)                           // 50 s: 30 s after the step
        assertFalse(vm.peek.value)
    }

    @Test
    fun an_alert_ends_the_peek_after_steps() {
        val src = FakeSource(listOf("a.jpg", "b.jpg"))
        val vm = withPhoto(src)
        vm.startPeek()
        vm.stepPhoto(+1)
        vm.stepPhoto(-1)
        scheduler.runCurrent()
        src.state = Fetch.Ok(demo("alert"))
        advance(5_000)
        assertFalse(vm.peek.value)
    }
}
