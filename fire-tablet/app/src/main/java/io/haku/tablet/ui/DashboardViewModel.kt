package io.haku.tablet.ui

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.haku.tablet.BuildConfig
import io.haku.tablet.data.Fetch
import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.NightDim
import io.haku.tablet.data.describe
import io.haku.tablet.ui.backdrop.AndroidPhotoDecoder
import io.haku.tablet.ui.backdrop.BackdropLoader
import io.haku.tablet.ui.backdrop.BgSettings
import io.haku.tablet.ui.backdrop.Photo
import io.haku.tablet.ui.backdrop.PhotoDecoder
import io.haku.tablet.ui.detail.DETAIL_AUTO_CLOSE_MS
import io.haku.tablet.ui.detail.DETAIL_REFRESH_MS
import io.haku.tablet.ui.detail.DetailContent
import io.haku.tablet.ui.detail.DetailUi
import io.haku.tablet.ui.detail.detailSettled
import io.haku.tablet.ui.detail.nextDetailContent
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.model.CardModel
import io.haku.tablet.ui.model.PollTracker
import io.haku.tablet.ui.model.Pulse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.coroutines.CoroutineContext

/**
 * [cards] is keyed by module id; it keeps the last good poll's cards through failures. [stateFetched] turns
 * true once the first /api/state fetch has completed, whether it succeeded or failed. [degraded] names the
 * modules whose card is stale at the last good poll, in config order ([PollResult]).
 */
data class UiState(
    val sidecar: String,
    val config: HubConfig? = null,
    val cards: Map<String, CardModel> = emptyMap(),
    val error: String? = null,
    val stateFetched: Boolean = false,
    val degraded: List<String> = emptyList(),
)

const val TAG = "KitchenWall"

/** One structured logcat line under [TAG]: `event=<name> k=v ...`. A failure's detail ends `err=<describe()>`. */
internal fun logEvent(name: String, detail: String) {
    Log.i(TAG, "event=$name $detail")
}

private const val STATE_EVERY_MS = 5_000L
private const val BACKOFF_MS = 30_000L
private const val BACKOFF_AFTER_FAILURES = 3
private const val CONFIG_EVERY_MS = 10 * 60_000L

/** A photo peek ends by itself after this long (v3 contract §3). */
const val PEEK_RETURN_MS = 30_000L

/**
 * Polls the sidecar: config at start + every 10 min, state every 5 s (30 s after 3 straight failures).
 * [clock] is the wall clock everything here reads, and [work] runs the per-poll projection off the main
 * thread; tests pass virtual time and their own context, and a [decoder] that needs no Android.
 */
class DashboardViewModel(
    private val source: HubSource,
    sidecarLabel: String = BuildConfig.SIDECAR_BASE,
    private val clock: () -> Long = System::currentTimeMillis,
    private val work: CoroutineContext = Dispatchers.Default,
    decoder: PhotoDecoder = AndroidPhotoDecoder(),
) : ViewModel() {

    private val _ui = MutableStateFlow(UiState(sidecar = sidecarLabel))
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private val _lastOkAt = MutableStateFlow<Long?>(null)

    /** Wall-clock ms of the last good /api/state, null until the first. Drives freshness. */
    val lastOkAt: StateFlow<Long?> = _lastOkAt.asStateFlow()

    /** [lastOkAt] as LIVE/LAGGING/OFFLINE. It changes only at those boundaries, with no per-second tick. */
    val freshness: StateFlow<Freshness> = freshnessFlow(lastOkAt, clock)
        .stateIn(viewModelScope, SharingStarted.Eagerly, Freshness.OFFLINE)

    /** Whether the house is inside the config's nightDim window now. Re-evaluated every minute and when the config changes. */
    val night: StateFlow<Boolean> = combine(
        _ui.map { it.config?.nightDim }.distinctUntilChanged(),
        minuteTicks(clock),
    ) { dim, now -> dim != null && isNight(minuteOfDay(now), dim.start, dim.end) }
        .stateIn(viewModelScope, SharingStarted.Eagerly, false)

    /** Window brightness (0..1) to hold while [night]. */
    val nightBrightness: Float
        get() = clampBrightness(_ui.value.config?.nightDim?.brightness ?: NightDim().brightness)

    private val backdrop = BackdropLoader(source, decoder, clock = clock, work = work)

    /** The NAS photo behind the cards, or null for the plain gradient (no config yet, disabled, empty NAS). */
    val photo: StateFlow<Photo?> = backdrop.photo

    private val _peek = MutableStateFlow(false)

    /**
     * Whether the photo peek is on: the UI and the scrim fade out so the photo shows bare. It ends on
     * [endPeek], after [PEEK_RETURN_MS], when the photo goes away, and on an alert.
     */
    val peek: StateFlow<Boolean> = _peek.asStateFlow()

    /** The pending auto-return of the current peek. Main thread only, like [startPeek] and [endPeek]. */
    private var peekReturn: Job? = null

    private val _detail = MutableStateFlow<DetailUi?>(null)

    /**
     * The open detail panel, or null. A panel refetches its detail every [DETAIL_REFRESH_MS] and closes by
     * itself after [DETAIL_AUTO_CLOSE_MS], so the wall always goes back to the glance; an alert closes it too.
     */
    val detail: StateFlow<DetailUi?> = _detail.asStateFlow()

    /** The open panel's fetch, refresh and auto-close. Main thread only, like [openDetail] and [closeDetail]. */
    private var detailJob: Job? = null

    /** Pulse and highlight baselines. Used only by the poll coroutine. */
    private val tracker = PollTracker { fired ->
        logEvent("pulse", fired.entries.joinToString(" ") { (id, p) -> "$id=${p.name.lowercase()}" })
        // Nothing may hide an alert. This runs on the poll's work context, so hop to the main thread.
        if (Pulse.ALERT in fired.values) viewModelScope.launch { closeOverlays() }
    }

    init {
        viewModelScope.launch { pollLoop() }
        viewModelScope.launch {
            backdrop.run(
                settings = _ui.map { it.config?.background?.let { b -> BgSettings(b.enabled, b.intervalMs) } },
            )
        }
        viewModelScope.launch {
            // No photo (backgrounds off, an empty NAS): nothing left to peek at.
            photo.collect { if (it == null) endPeek() }
        }
    }

    /** Starts a photo peek, which returns by itself after [PEEK_RETURN_MS]. Does nothing without a photo. */
    fun startPeek() {
        if (photo.value == null) return
        peekReturn?.cancel()
        _peek.value = true
        peekReturn = viewModelScope.launch {
            delay(PEEK_RETURN_MS)
            _peek.value = false
        }
    }

    /** Ends the photo peek, if one is on. */
    fun endPeek() {
        peekReturn?.cancel()
        peekReturn = null
        _peek.value = false
    }

    /**
     * Opens the detail panel for module [id] (a module the config doesn't know is ignored), and ends any peek.
     * Calendar and Activity lay out the items the tablet already has; every other module fetches the sidecar's
     * detail, showing its live tile meanwhile.
     */
    fun openDetail(id: String) {
        if (_ui.value.config?.modules?.any { it.id == id } != true) return
        endPeek()
        detailJob?.cancel()
        val local = _ui.value.cards[id] is AgendaModel
        _detail.value = DetailUi(id, if (local) DetailContent.Local else DetailContent.Loading)
        logEvent("detail_open", "id=$id")
        detailJob = viewModelScope.launch {
            launch {
                delay(DETAIL_AUTO_CLOSE_MS)
                closeDetail()
            }
            if (local) return@launch
            while (true) {
                val r = source.detail(id)
                val open = _detail.value?.takeIf { it.id == id } ?: return@launch
                val next = nextDetailContent(open.content, r)
                _detail.value = open.copy(content = next)
                if (r !is Fetch.Ok) logEvent("detail_fail", "id=$id err=${r.describe()}")
                if (detailSettled(next)) return@launch
                delay(DETAIL_REFRESH_MS)
            }
        }
    }

    /** Closes the detail panel, if one is open. */
    fun closeDetail() {
        if (_detail.value == null) return
        logEvent("detail_close", "id=${_detail.value?.id}")
        _detail.value = null
        detailJob?.cancel()
        detailJob = null
    }

    /** Ends whatever hides the cards: the detail panel and the peek. */
    private fun closeOverlays() {
        closeDetail()
        endPeek()
    }

    private suspend fun pollLoop() {
        var configAt = 0L
        var failures = 0
        while (viewModelScope.isActive) {
            val now = clock()
            if (_ui.value.config == null || now - configAt > CONFIG_EVERY_MS) {
                when (val r = source.config()) {
                    is Fetch.Ok -> {
                        configAt = now
                        _ui.update { it.copy(config = r.value) }
                        logEvent("config_loaded", "modules=${r.value.modules.size}")
                    }
                    else -> {
                        _ui.update { it.copy(error = r.describe()) }
                        logEvent("config_fail", "err=${r.describe()}")
                    }
                }
            }
            when (val r = source.state()) {
                is Fetch.Ok -> {
                    failures = 0
                    val config = _ui.value.config
                    val polled = config?.let { withContext(work) { tracker.onOk(it, r.value, clock()) } }
                    _ui.update {
                        it.copy(
                            cards = polled?.cards ?: it.cards,
                            degraded = polled?.degraded ?: it.degraded,
                            error = null,
                            stateFetched = true,
                        )
                    }
                    _lastOkAt.value = clock()
                    logEvent("poll_ok", "ts=${r.value.ts}")
                }
                else -> {
                    failures++
                    tracker.onFail()
                    _ui.update { it.copy(error = r.describe(), stateFetched = true) }
                    logEvent("poll_fail", "n=$failures err=${r.describe()}")
                }
            }
            delay(if (failures >= BACKOFF_AFTER_FAILURES) BACKOFF_MS else STATE_EVERY_MS)
        }
    }
}
