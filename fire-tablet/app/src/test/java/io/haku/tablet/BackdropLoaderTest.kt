package io.haku.tablet

import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.ImageBitmapConfig
import androidx.compose.ui.graphics.colorspace.ColorSpace
import androidx.compose.ui.graphics.colorspace.ColorSpaces
import io.haku.tablet.data.Fetch
import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.HubState
import io.haku.tablet.ui.backdrop.BackdropLoader
import io.haku.tablet.ui.backdrop.BgSettings
import io.haku.tablet.ui.backdrop.Photo
import io.haku.tablet.ui.backdrop.PhotoDecoder
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.random.Random

@OptIn(ExperimentalCoroutinesApi::class)
class BackdropLoaderTest {
    /** The sidecar's background routes. Image bytes are `name|width`, so the fake decoder can tell what it got. */
    private class FakeSource(names: List<String>) : HubSource {
        var list: Fetch<List<String>> = Fetch.Ok(names)
        var emptyBodies = false
        var listCalls = 0
        val imageCalls = mutableListOf<String>()

        override suspend fun config(): Fetch<HubConfig> = error("unused")
        override suspend fun state(): Fetch<HubState> = error("unused")
        override suspend fun backgrounds(): Fetch<List<String>> {
            listCalls++
            return list
        }
        override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> {
            imageCalls += "$name $w $h $fit $blur"
            // A 200 with an empty body is still Ok: the decoder has to reject it.
            return Fetch.Ok(if (emptyBodies) ByteArray(0) else "$name|$w".encodeToByteArray())
        }
    }

    private class FakeDecoder : PhotoDecoder {
        val badSoft = mutableSetOf<String>()
        var throwOom = false
        var oomThrown = 0

        override fun sharp(bytes: ByteArray): ImageBitmap? = decode(bytes)
        override fun soft(bytes: ByteArray): Pair<ImageBitmap, Float>? =
            decode(bytes)?.takeIf { it.name !in badSoft }?.let { it to LUMA }

        private fun decode(bytes: ByteArray): FakeImage? {
            if (throwOom) {
                oomThrown++
                throw OutOfMemoryError("fake")
            }
            if (bytes.isEmpty()) return null   // what BitmapFactory does with an empty body
            val (name, w) = bytes.decodeToString().split("|")
            return FakeImage(name, w.toInt())
        }
    }

    private class FakeImage(val name: String, override val width: Int) : ImageBitmap {
        override val height = width * 600 / 1024
        override val colorSpace: ColorSpace = ColorSpaces.Srgb
        override val hasAlpha = false
        override val config = ImageBitmapConfig.Argb8888
        override fun readPixels(
            buffer: IntArray, startX: Int, startY: Int, width: Int, height: Int, bufferOffset: Int, stride: Int,
        ) = Unit
        override fun prepareToDraw() = Unit
    }

    private val Photo.name get() = (sharp as FakeImage).name

    private fun TestScope.loader(source: HubSource, decoder: PhotoDecoder = FakeDecoder()) =
        BackdropLoader(source, decoder, Random(11), clock = { testScheduler.currentTime }, work = EmptyCoroutineContext)

    private fun TestScope.start(
        loader: BackdropLoader,
        settings: Flow<BgSettings?> = flowOf(ON),
        hold: StateFlow<Boolean> = MutableStateFlow(false),
    ) {
        backgroundScope.launch { loader.run(settings, hold) }
        runCurrent()
    }

    /** Advances virtual time by [ms] and runs whatever falls due at the new instant. */
    private fun TestScope.advance(ms: Long) {
        advanceTimeBy(ms)
        runCurrent()
    }

    @Test
    fun `emits_photo_after_both_variants_decode`() = runTest {
        val src = FakeSource(listOf("a.jpg"))
        val dec = FakeDecoder().apply { badSoft += "a.jpg" }
        val loader = loader(src, dec)
        start(loader)
        assertNull("the sharp decoded but the soft did not: no swap", loader.photo.value)
        assertEquals(listOf("a.jpg 1024 600 cover 0", "a.jpg 256 150 cover 8"), src.imageCalls)

        dec.badSoft.clear()
        advance(60_000)   // one miss backs off a minute
        val p = assertNotNull(loader.photo.value)
        assertEquals("a.jpg", p.name)
        assertEquals(1024, p.sharp.width)
        assertEquals(256, p.soft.width)
        assertEquals(LUMA, p.luma)
    }

    @Test
    fun `disabled_emits_null`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg"))
        val settings = MutableStateFlow<BgSettings?>(BgSettings(enabled = false, intervalMs = 180_000))
        val loader = loader(src)
        start(loader, settings)
        assertNull(loader.photo.value)
        assertEquals("disabled never lists", 0, src.listCalls)

        settings.value = ON
        runCurrent()
        assertNotNull(loader.photo.value)

        settings.value = BgSettings(enabled = false, intervalMs = 180_000)
        runCurrent()
        assertNull(loader.photo.value)
        val calls = src.imageCalls.size
        advance(30 * 60_000)
        assertEquals("disabled stops rotating", calls, src.imageCalls.size)

        settings.value = null   // no config yet, or one without a background block
        runCurrent()
        assertNull(loader.photo.value)
    }

    @Test
    fun `empty_list_emits_null`() = runTest {
        val empty = FakeSource(emptyList())
        val cold = loader(empty)
        start(cold)
        assertNull(cold.photo.value)
        assertTrue(empty.imageCalls.isEmpty())

        // The NAS emptied (or unmounted) mid-run: the next list refresh drops back to the gradient.
        val src = FakeSource(listOf("a.jpg", "b.jpg"))
        val loader = loader(src)
        start(loader)
        assertNotNull(loader.photo.value)
        src.list = Fetch.Ok(emptyList())
        advance(12 * 60_000)   // rotations at 3, 6, 9 min; the 12 min one re-lists
        assertNull(loader.photo.value)
    }

    @Test
    fun `bad_file_keeps_current_photo`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg"))
        val dec = FakeDecoder()
        val loader = loader(src, dec)
        start(loader, flowOf(BgSettings(enabled = true, intervalMs = 300_000)))
        val first = assertNotNull(loader.photo.value)

        src.emptyBodies = true   // 200 with no body
        advance(300_000)
        assertSame(first, loader.photo.value)

        src.emptyBodies = false
        dec.throwOom = true      // a decode that runs out of memory
        advance(60_000)          // first miss: 1 min backoff, not the 5 min interval
        assertEquals(1, dec.oomThrown)
        assertSame(first, loader.photo.value)

        dec.throwOom = false
        advance(119_999)         // second miss: 2 min backoff
        assertSame(first, loader.photo.value)
        advance(1)
        val next = assertNotNull(loader.photo.value)
        assertNotSame(first, next)
    }

    @Test
    fun `list_failure_keeps_old_names`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg"))
        val loader = loader(src)
        start(loader)
        assertEquals(1, src.listCalls)

        src.list = Fetch.NetworkError("sidecar down")
        advance(9 * 60_000)
        val before = loader.photo.value
        advance(3 * 60_000)      // 12 min: the refresh fails
        assertEquals(2, src.listCalls)
        val after = assertNotNull(loader.photo.value)
        assertNotSame("still rotating through the old names", before, after)
        assertTrue(after.name in setOf("a.jpg", "b.jpg"))

        advance(3 * 60_000)      // a failed refresh is retried on the next rotation
        assertEquals(3, src.listCalls)
        assertNotSame(after, loader.photo.value)
    }

    @Test
    fun `rotates_after_interval`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg", "c.jpg"))
        val loader = loader(src)
        start(loader)
        val first = assertNotNull(loader.photo.value)

        advance(179_999)
        assertSame(first, loader.photo.value)
        advance(1)
        val second = assertNotNull(loader.photo.value)
        assertTrue("no immediate repeat", second.name != first.name)

        // An interval under a minute is held at a minute.
        val fast = loader(FakeSource(listOf("a.jpg", "b.jpg")))
        start(fast, flowOf(BgSettings(enabled = true, intervalMs = 1_000)))
        val p = fast.photo.value
        advance(59_999)
        assertSame(p, fast.photo.value)
        advance(1)
        assertNotSame(p, fast.photo.value)
    }

    /** Steps by [delta] and runs the load it starts. */
    private fun TestScope.step(loader: BackdropLoader, delta: Int) {
        loader.step(delta)
        runCurrent()
    }

    private fun BackdropLoader.name() = assertNotNull(photo.value).name

    /** Names of the sharp variants fetched so far, in order: one per photo load. */
    private val FakeSource.loads get() = imageCalls.filter { it.contains(" 1024 ") }.map { it.substringBefore(' ') }

    @Test
    fun `step_back_shows_the_previous_photo_and_forward_retraces`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg", "c.jpg", "d.jpg"))
        val loader = loader(src)
        start(loader)
        val first = loader.name()
        step(loader, +1)
        val second = loader.name()
        assertTrue("forward deals a new photo", second != first)

        step(loader, -1)
        assertEquals(first, loader.name())
        step(loader, +1)
        assertEquals("forward retraces the history, not a new deal", second, loader.name())
        assertEquals(listOf(first, second, first, second), src.loads)
    }

    @Test
    fun `step_back_at_the_oldest_does_nothing`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg"))
        val loader = loader(src)
        start(loader)
        val p = loader.photo.value
        val calls = src.imageCalls.size
        step(loader, -1)
        assertSame(p, loader.photo.value)
        assertEquals("no fetch", calls, src.imageCalls.size)
    }

    @Test
    fun `queued_steps_load_only_the_final_photo`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"))
        val loader = loader(src)
        start(loader)
        val calls = src.imageCalls.size
        loader.step(+1)
        loader.step(+1)
        loader.step(+1)
        runCurrent()
        assertEquals("one load: both variants of the third photo dealt", calls + 2, src.imageCalls.size)

        // The two skipped photos are still on the reel: back walks through them.
        val last = loader.name()
        step(loader, -1)
        assertTrue(loader.name() != last)
    }

    @Test
    fun `history_keeps_the_last_20`() = runTest {
        val names = List(30) { "p$it.jpg" }
        val src = FakeSource(names)
        val loader = loader(src)
        start(loader)
        repeat(24) { step(loader, +1) }   // 25 shown
        val shown = src.loads
        assertEquals(25, shown.size)
        repeat(30) { step(loader, -1) }
        assertEquals("back stops at the oldest kept", shown[5], loader.name())
    }

    @Test
    fun `failed_step_keeps_the_current_photo`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg", "c.jpg"))
        val loader = loader(src)
        start(loader)
        val p = loader.photo.value
        src.emptyBodies = true
        step(loader, +1)
        assertSame(p, loader.photo.value)

        // The failed photo left the reel: back from here has nowhere to go.
        src.emptyBodies = false
        val calls = src.imageCalls.size
        step(loader, -1)
        assertSame(p, loader.photo.value)
        assertEquals(calls, src.imageCalls.size)
    }

    @Test
    fun `hold_pauses_rotation`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg", "c.jpg"))
        val hold = MutableStateFlow(true)
        val loader = loader(src)
        start(loader, hold = hold)
        val p = loader.photo.value
        advance(180_000)
        assertSame("no auto-advance while held", p, loader.photo.value)

        hold.value = false
        advance(179_999)
        assertSame("the held timer re-armed a full interval", p, loader.photo.value)
        advance(1)
        assertNotSame(p, loader.photo.value)
    }

    @Test
    fun `step_restarts_the_interval`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg", "c.jpg"))
        val loader = loader(src)
        start(loader)
        advance(100_000)
        step(loader, +1)
        val p = loader.photo.value
        advance(179_999)
        assertSame(p, loader.photo.value)
        advance(1)
        assertNotSame(p, loader.photo.value)
    }

    @Test
    fun `rotation_after_stepping_back_drops_the_forward_history`() = runTest {
        val src = FakeSource(listOf("a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"))
        val loader = loader(src)
        start(loader)
        val first = loader.name()
        step(loader, +1)
        step(loader, +1)
        step(loader, -1)
        step(loader, -1)
        assertEquals(first, loader.name())
        advance(180_000)                     // rotation deals a new photo after the first
        val dealt = loader.name()
        step(loader, -1)
        assertEquals(first, loader.name())
        step(loader, +1)
        assertEquals("forward retraces to the dealt photo, not the dropped ones", dealt, loader.name())
    }

    private fun <T> assertNotNull(value: T?): T {
        org.junit.Assert.assertNotNull(value)
        return value!!
    }

    private fun <T> assertNotNull(message: String, value: T?): T {
        org.junit.Assert.assertNotNull(message, value)
        return value!!
    }

    private companion object {
        const val LUMA = 0.4f
        val ON = BgSettings(enabled = true, intervalMs = 180_000)
    }
}
