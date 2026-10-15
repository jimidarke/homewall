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
import io.haku.tablet.ui.Freshness
import io.haku.tablet.ui.model.CardModel
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.model.HOLD_GRACE_MS
import io.haku.tablet.ui.model.ValueModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import kotlin.coroutines.EmptyCoroutineContext

/**
 * The poll loop, the kiosk's whole resilience path, on virtual time. The view model's tickers (freshness,
 * the minute clock, the backdrop loader) never go idle, so every step advances time by an explicit amount.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class DashboardViewModelTest {
    private val scheduler = TestCoroutineScheduler()
    private val store = ViewModelStore()

    private val demoDir = File("src/debug/assets/demo")
    private val config = HubJson.parseConfig(File(demoDir, "config.json").readText())
    private fun demo(name: String): HubState = HubJson.parseState(File(demoDir, "$name.json").readText())

    /** A scripted sidecar. Each call records the virtual time it was made at. The NAS is empty, so the backdrop stays idle. */
    private inner class FakeSource : HubSource {
        var config: Fetch<HubConfig> = Fetch.NetworkError("refused")
        var state: Fetch<HubState> = Fetch.NetworkError("refused")

        /** How long a state fetch takes, so a test can look at the UI between the config and state fetches. */
        var stateLatencyMs = 0L
        val configCalls = mutableListOf<Long>()
        val stateCalls = mutableListOf<Long>()

        override suspend fun config(): Fetch<HubConfig> {
            configCalls += scheduler.currentTime
            return config
        }

        override suspend fun state(): Fetch<HubState> {
            stateCalls += scheduler.currentTime
            if (stateLatencyMs > 0) delay(stateLatencyMs)
            return state
        }

        override suspend fun backgrounds(): Fetch<List<String>> = Fetch.Ok(emptyList())
        override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> =
            error("unused: the NAS list is empty")
    }

    @Before
    fun setUp() = Dispatchers.setMain(StandardTestDispatcher(scheduler))

    @After
    fun tearDown() {
        store.clear()   // cancels viewModelScope, so nothing outlives the test
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

    /** Advances virtual time by [ms] and runs whatever falls due at the new instant. */
    private fun advance(ms: Long) {
        scheduler.advanceTimeBy(ms)
        scheduler.runCurrent()
    }

    private fun base(c: CardModel?): ValueModel? = when (c) {
        is ValueModel -> c
        is DoorsModel -> c.base
        is LaundryModel -> c.base
        else -> null   // agenda cards never pulse
    }

    private fun assertNoPulses(cards: Map<String, CardModel>) {
        for ((id, c) in cards) {
            val b = base(c) ?: continue
            assertEquals("$id seq", 0, b.pulseSeq)
            assertEquals("$id count", 0, b.pulseCount)
        }
    }

    @Test
    fun sidecar_down_at_cold_start_sets_error_and_backs_off() {
        val src = FakeSource()
        val vm = viewModel(src)
        assertFalse("nothing fetched before the loop first runs", vm.ui.value.stateFetched)

        scheduler.runCurrent()
        with(vm.ui.value) {
            assertEquals("network: refused", error)
            assertTrue(stateFetched)
            assertNull(config)
            assertTrue(cards.isEmpty())
        }
        assertNull(vm.lastOkAt.value)
        assertEquals(Freshness.OFFLINE, vm.freshness.value)

        advance(62_000)
        // Every 1 s until the third straight failure, then every 30 s.
        assertEquals(listOf(0L, 1_000L, 2_000L, 32_000L, 62_000L), src.stateCalls)
        // With no config yet, every poll asks for it first.
        assertEquals(src.stateCalls, src.configCalls)
        assertEquals("network: refused", vm.ui.value.error)
    }

    @Test
    fun recovery_from_cold_start_outage_shows_cards_without_pulses() {
        val src = FakeSource()
        val vm = viewModel(src)
        advance(32_000)   // fails at 0, 1, 2 and 32 s: backed off
        assertEquals(listOf(0L, 1_000L, 2_000L, 32_000L), src.stateCalls)

        src.config = Fetch.Ok(config)
        src.state = Fetch.Ok(demo("busy"))
        advance(30_000)   // the 62 s poll comes back
        with(vm.ui.value) {
            assertSame(this@DashboardViewModelTest.config, config)
            assertNull(error)
            assertTrue(stateFetched)
            assertEquals(config!!.modules.map { it.id }.toSet(), cards.keys)
            assertNoPulses(cards)   // a busy house at the first good poll is the baseline, not a change
        }
        assertEquals(62_000L, vm.lastOkAt.value)
        assertEquals(Freshness.LIVE, vm.freshness.value)

        advance(1_000)    // back on the 1 s cadence
        assertEquals(63_000L, src.stateCalls.last())
        assertNoPulses(vm.ui.value.cards)
    }

    @Test
    fun mid_run_outage_keeps_cards_and_recovers_without_pulses() {
        val src = FakeSource().apply {
            config = Fetch.Ok(this@DashboardViewModelTest.config)
            state = Fetch.Ok(demo("quiet"))
        }
        val vm = viewModel(src)
        advance(5_000)
        val quiet = vm.ui.value.cards
        assertTrue(quiet.isNotEmpty())

        src.state = Fetch.HttpError(502)
        advance(1_000)
        with(vm.ui.value) {
            assertEquals("http 502", error)
            assertSame("the last good cards stay up through a failure", quiet, cards)
        }

        // The house got busy during the gap. The gap re-baselines, so nothing rings for it.
        src.state = Fetch.Ok(demo("busy"))
        advance(1_000)
        with(vm.ui.value) {
            assertNull(error)
            assertTrue(cards.values.any { base(it)?.active == true })
            assertNoPulses(cards)
        }
    }

    @Test
    fun degraded_follows_good_polls_and_holds_through_a_failure() {
        val src = FakeSource().apply {
            config = Fetch.Ok(this@DashboardViewModelTest.config)
            state = Fetch.Ok(demo("quiet"))
        }
        val vm = viewModel(src)
        scheduler.runCurrent()
        assertEquals(emptyList<String>(), vm.ui.value.degraded)

        src.state = Fetch.Ok(demo("degraded"))
        advance(5_000)
        assertEquals("a short dropout isn't degraded yet", emptyList<String>(), vm.ui.value.degraded)
        assertFalse((vm.ui.value.cards["water"] as ValueModel).stale)
        advance(HOLD_GRACE_MS)
        with(vm.ui.value) {
            assertEquals(listOf("Water"), degraded)
            val water = cards["water"] as ValueModel
            assertEquals("quiet's reading, held", "27 L", water.hero)
            assertTrue(water.stale)
            assertNotNull(water.asOf)
        }

        src.state = Fetch.HttpError(502)
        advance(1_000)
        assertEquals("a failed poll leaves it as it was", listOf("Water"), vm.ui.value.degraded)

        src.state = Fetch.Ok(demo("quiet"))
        advance(1_000)
        assertEquals(emptyList<String>(), vm.ui.value.degraded)
        assertNull((vm.ui.value.cards["water"] as ValueModel).asOf)
    }

    @Test
    fun config_reload_failure_keeps_old_config() {
        val src = FakeSource().apply {
            config = Fetch.Ok(this@DashboardViewModelTest.config)
            state = Fetch.Ok(demo("quiet"))
        }
        val vm = viewModel(src)
        scheduler.runCurrent()
        assertSame(config, vm.ui.value.config)

        advance(600_000)   // a reload is due once 10 min have passed, strictly
        assertEquals(listOf(0L), src.configCalls)

        src.config = Fetch.HttpError(502)
        src.stateLatencyMs = 100
        advance(1_000)     // 601 s: the reload fails, and the state fetch is still in flight
        assertEquals(listOf(0L, 601_000L), src.configCalls)
        with(vm.ui.value) {
            assertSame("the old config stays", this@DashboardViewModelTest.config, config)
            assertEquals("http 502", error)
            assertTrue(cards.isNotEmpty())
        }

        advance(100)       // the good state clears the error
        with(vm.ui.value) {
            assertSame(this@DashboardViewModelTest.config, config)
            assertNull(error)
            assertTrue(cards.isNotEmpty())
        }
        assertEquals(601_100L, vm.lastOkAt.value)

        // A failed reload is retried on the next poll, not 10 min later. Once it succeeds, the next is 10 min on.
        src.config = Fetch.Ok(config)
        src.stateLatencyMs = 0
        advance(1_000)
        assertEquals(listOf(0L, 601_000L, 602_100L), src.configCalls)
        advance(600_000)
        assertEquals(listOf(0L, 601_000L, 602_100L), src.configCalls)
        advance(1_000)
        assertEquals(listOf(0L, 601_000L, 602_100L, 1_203_100L), src.configCalls)
    }
}
