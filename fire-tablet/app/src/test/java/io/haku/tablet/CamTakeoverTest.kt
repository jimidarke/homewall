package io.haku.tablet

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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import java.io.File
import kotlin.coroutines.EmptyCoroutineContext

/**
 * The door camera takeover in the view model, on virtual time. The sidecar's doors module carries
 * `takeover: {cam, hls, label, until}` for 60 s after the front door opens; the tablet shows it full screen
 * until `until` (measured against the state's own `ts`, so the tablet's clock doesn't matter).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class CamTakeoverTest {
    private val scheduler = TestCoroutineScheduler()
    private val store = ViewModelStore()

    private val demoDir = File("src/debug/assets/demo")
    private val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
    private fun demoJson(name: String): String = File(demoDir, "$name.json").readText()
    private fun demo(name: String): HubState = HubJson.parseState(demoJson(name))

    private val quietTs = 1_790_822_530L          // quiet.json's ts

    /** [base] (quiet.json by default) with the doors module carrying a takeover that ends at [until], at [ts]. */
    private fun withTakeover(until: Long, ts: Long = quietTs, base: String = "quiet"): HubState {
        val root = HubJson.json.parseToJsonElement(demoJson(base)).jsonObject
        val doors = root.getValue("doors").jsonObject
        val takeover = buildJsonObject {
            put("cam", "front_steps")
            put("hls", "http://192.0.2.20:1985/hls/front_steps.m3u8")
            put("label", "Front Steps")
            put("until", until)
        }
        val patched = JsonObject(root + ("ts" to JsonPrimitive(ts)) + ("doors" to JsonObject(doors + ("takeover" to takeover))))
        return HubJson.parseState(patched.toString())
    }

    private inner class FakeSource : HubSource {
        var state: Fetch<HubState> = Fetch.Ok(demo("quiet"))
        override suspend fun config(): Fetch<HubConfig> = Fetch.Ok(this@CamTakeoverTest.config)
        override suspend fun state(): Fetch<HubState> = state
        override suspend fun backgrounds(): Fetch<List<String>> = Fetch.Ok(emptyList())
        override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> =
            error("unused: no photos")
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
                DashboardViewModel(source, "test", clock = { scheduler.currentTime }, work = EmptyCoroutineContext)
            }
        }
        return ViewModelProvider(store, factory)[DashboardViewModel::class.java]
    }

    private fun advance(ms: Long) {
        scheduler.advanceTimeBy(ms)
        scheduler.runCurrent()
    }

    @Test
    fun opens_on_a_takeover_and_closes_at_until() {
        val src = FakeSource()
        val vm = viewModel(src)
        advance(1_500)
        assertNull(vm.cam.value)

        src.state = Fetch.Ok(withTakeover(until = quietTs + 60))
        advance(1_000)
        val cam = vm.cam.value!!
        assertEquals("http://192.0.2.20:1985/hls/front_steps.m3u8", cam.hls)
        assertEquals("Front Steps", cam.label)

        advance(58_000)
        assertNotNull(vm.cam.value)
        advance(2_000)
        assertNull(vm.cam.value)                   // 60 s of the sidecar's clock
        advance(5_000)
        assertNull(vm.cam.value)                   // the same opening never reopens
    }

    @Test
    fun a_tap_closes_it_for_good() {
        val src = FakeSource()
        val vm = viewModel(src)
        src.state = Fetch.Ok(withTakeover(until = quietTs + 60))
        advance(1_500)
        assertNotNull(vm.cam.value)
        vm.closeCam()
        advance(5_000)
        assertNull(vm.cam.value)
    }

    @Test
    fun the_remaining_time_follows_the_sidecar_clock() {
        val src = FakeSource()
        val vm = viewModel(src)
        src.state = Fetch.Ok(withTakeover(until = quietTs + 20))   // opened 40 s before this poll
        advance(1_500)
        assertNotNull(vm.cam.value)
        advance(21_000)
        assertNull(vm.cam.value)
    }

    @Test
    fun an_expired_takeover_never_opens() {
        val src = FakeSource()
        val vm = viewModel(src)
        src.state = Fetch.Ok(withTakeover(until = quietTs))
        advance(3_000)
        assertNull(vm.cam.value)
    }

    @Test
    fun an_alert_closes_it() {
        val src = FakeSource()
        val vm = viewModel(src)
        advance(1_500)                              // a quiet baseline, so the alert is an edge
        src.state = Fetch.Ok(withTakeover(until = quietTs + 60))
        advance(1_000)
        assertNotNull(vm.cam.value)
        src.state = Fetch.Ok(demo("alert"))
        advance(2_000)
        assertNull(vm.cam.value)                    // nothing may hide an alert
    }

    @Test
    fun an_alert_in_the_same_poll_keeps_it_closed() {
        val src = FakeSource()
        val vm = viewModel(src)
        advance(1_500)                              // a quiet baseline, so the alert is an edge
        src.state = Fetch.Ok(withTakeover(until = quietTs + 60, base = "alert"))
        advance(1_000)
        assertNull(vm.cam.value)                    // nothing may hide an alert, even one in the same poll
        advance(1_000)
        assertNull(vm.cam.value)                    // nor on the next poll: that opening is spent
    }

    @Test
    fun a_stream_error_closes_it_and_a_new_opening_reopens() {
        val src = FakeSource()
        val vm = viewModel(src)
        src.state = Fetch.Ok(withTakeover(until = quietTs + 60))
        advance(1_500)
        vm.camFailed()
        assertNull(vm.cam.value)
        src.state = Fetch.Ok(withTakeover(until = quietTs + 90, ts = quietTs + 30))   // the door opened again
        advance(1_000)
        assertNotNull(vm.cam.value)
    }

    @Test
    fun a_takeover_ends_any_peek_or_panel() {
        val src = FakeSource()
        val vm = viewModel(src)
        advance(1_500)
        vm.openDetail("water")
        assertNotNull(vm.detail.value)
        src.state = Fetch.Ok(withTakeover(until = quietTs + 60))
        advance(1_000)
        assertNotNull(vm.cam.value)
        assertNull(vm.detail.value)
    }
}
