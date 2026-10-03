package io.haku.tablet

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import io.haku.tablet.data.Detail
import io.haku.tablet.data.Fetch
import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubJson
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.HubState
import io.haku.tablet.ui.DashboardViewModel
import io.haku.tablet.ui.backdrop.PhotoDecoder
import io.haku.tablet.ui.detail.DETAIL_AUTO_CLOSE_MS
import io.haku.tablet.ui.detail.DETAIL_FAILED_NOTE
import io.haku.tablet.ui.detail.DETAIL_REFRESH_MS
import io.haku.tablet.ui.detail.DetailContent
import io.haku.tablet.ui.detail.nextDetailContent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import kotlin.coroutines.EmptyCoroutineContext

/** The detail panel's open, fetch, refresh and close in the view model, on virtual time, with the demo house. */
@OptIn(ExperimentalCoroutinesApi::class)
class DetailVmTest {
    private val scheduler = TestCoroutineScheduler()
    private val store = ViewModelStore()
    private val demoDir = File("src/debug/assets/demo")
    private val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
    private fun demo(name: String): HubState = HubJson.parseState(File(demoDir, "$name.json").readText())
    private val water: Detail = io.haku.tablet.data.parseDetail(File(demoDir, "detail_water.json").readText())

    private inner class FakeSource : HubSource {
        var state: Fetch<HubState> = Fetch.Ok(demo("quiet"))
        var detail: Fetch<Detail> = Fetch.Ok(water)
        val detailCalls = mutableListOf<String>()
        override suspend fun config(): Fetch<HubConfig> = Fetch.Ok(this@DetailVmTest.config)
        override suspend fun state(): Fetch<HubState> = state
        override suspend fun backgrounds(): Fetch<List<String>> = Fetch.Ok(emptyList())
        override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> =
            Fetch.HttpError(404)
        override suspend fun detail(id: String): Fetch<Detail> {
            detailCalls += id
            return detail
        }
    }

    private object NoDecoder : PhotoDecoder {
        override fun sharp(bytes: ByteArray) = error("no photos here")
        override fun soft(bytes: ByteArray) = error("no photos here")
    }

    @Before
    fun setUp() = Dispatchers.setMain(StandardTestDispatcher(scheduler))

    @After
    fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
    }

    private fun viewModel(source: HubSource): DashboardViewModel {
        val factory = viewModelFactory {
            initializer {
                DashboardViewModel(
                    source, "test",
                    clock = { 1_790_000_000_000L + scheduler.currentTime },
                    work = EmptyCoroutineContext,
                    decoder = NoDecoder,
                )
            }
        }
        return ViewModelProvider(store, factory)[DashboardViewModel::class.java].also { scheduler.runCurrent() }
    }

    private fun advance(ms: Long) {
        scheduler.advanceTimeBy(ms)
        scheduler.runCurrent()
    }

    @Test
    fun a_value_card_shows_its_tile_then_the_fetched_detail() {
        val src = FakeSource()
        val vm = viewModel(src)
        vm.openDetail("water")
        assertEquals(DetailContent.Loading, vm.detail.value?.content)
        scheduler.runCurrent()
        assertEquals(DetailContent.Loaded(water), vm.detail.value?.content)
        assertEquals(listOf("water"), src.detailCalls)
    }

    @Test
    fun agenda_cards_lay_out_their_own_items_without_a_fetch() {
        val src = FakeSource()
        val vm = viewModel(src)
        val agenda = config.modules.first { it.tile.type == "agenda" }.id
        vm.openDetail(agenda)
        scheduler.runCurrent()
        assertEquals(DetailContent.Local, vm.detail.value?.content)
        assertTrue(src.detailCalls.isEmpty())
    }

    @Test
    fun unknown_modules_open_nothing() {
        val vm = viewModel(FakeSource())
        vm.openDetail("no-such-module")
        assertNull(vm.detail.value)
    }

    @Test
    fun refreshes_every_minute_and_closes_by_itself() {
        val src = FakeSource()
        val vm = viewModel(src)
        vm.openDetail("water")
        scheduler.runCurrent()
        advance(DETAIL_REFRESH_MS)
        assertEquals(2, src.detailCalls.size)
        advance(DETAIL_AUTO_CLOSE_MS - DETAIL_REFRESH_MS - 1)
        assertEquals("water", vm.detail.value?.id)
        advance(1)
        assertNull(vm.detail.value)
        val calls = src.detailCalls.size
        advance(5 * DETAIL_REFRESH_MS)
        assertEquals("a closed panel stops fetching", calls, src.detailCalls.size)
    }

    @Test
    fun a_404_shows_the_tile_and_stops_fetching() {
        val src = FakeSource().apply { detail = Fetch.HttpError(404) }
        val vm = viewModel(src)
        vm.openDetail("water")
        scheduler.runCurrent()
        assertEquals(DetailContent.Unavailable(null), vm.detail.value?.content)
        advance(DETAIL_REFRESH_MS)
        assertEquals(1, src.detailCalls.size)
    }

    @Test
    fun a_failure_says_so_and_retries_a_minute_later() {
        val src = FakeSource().apply { detail = Fetch.NetworkError("timeout") }
        val vm = viewModel(src)
        vm.openDetail("water")
        scheduler.runCurrent()
        assertEquals(DetailContent.Unavailable(DETAIL_FAILED_NOTE), vm.detail.value?.content)
        src.detail = Fetch.Ok(water)
        advance(DETAIL_REFRESH_MS)
        assertEquals(DetailContent.Loaded(water), vm.detail.value?.content)
        // A failed refresh keeping the loaded detail is next_content_rules; the next refresh (120 s) is past
        // the 90 s auto-close.
    }

    @Test
    fun close_and_reopen() {
        val vm = viewModel(FakeSource())
        vm.openDetail("water")
        vm.closeDetail()
        assertNull(vm.detail.value)
        vm.closeDetail()   // twice is harmless
        vm.openDetail("energy")
        assertEquals("energy", vm.detail.value?.id)
    }

    @Test
    fun an_alert_closes_the_panel() {
        val src = FakeSource()
        val vm = viewModel(src)
        vm.openDetail("water")
        scheduler.runCurrent()
        src.state = Fetch.Ok(demo("busy"))
        advance(5_000)
        assertEquals("activity alone leaves the panel up", "water", vm.detail.value?.id)
        src.state = Fetch.Ok(demo("alert"))
        advance(5_000)
        assertNull("an alert must never hide behind a panel", vm.detail.value)
    }

    @Test
    fun next_content_rules() {
        val loaded = DetailContent.Loaded(water)
        assertEquals(loaded, nextDetailContent(DetailContent.Loading, Fetch.Ok(water)))
        assertEquals(DetailContent.Unavailable(null), nextDetailContent(loaded, Fetch.HttpError(404)))
        assertEquals(loaded, nextDetailContent(loaded, Fetch.ParseError("x")))
        assertEquals(
            DetailContent.Unavailable(DETAIL_FAILED_NOTE),
            nextDetailContent(DetailContent.Loading, Fetch.HttpError(500)),
        )
    }
}
