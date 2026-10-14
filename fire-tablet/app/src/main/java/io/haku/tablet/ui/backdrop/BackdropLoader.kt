package io.haku.tablet.ui.backdrop

import io.haku.tablet.data.Fetch
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.describe
import io.haku.tablet.ui.logEvent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.CoroutineContext
import kotlin.random.Random

/** The config's `background` block, as the loader needs it. */
data class BgSettings(val enabled: Boolean, val intervalMs: Long)

/**
 * Rotates the sidecar's photos behind the cards. [photo] is the current one, or null for the plain gradient
 * (no config yet, backgrounds disabled, or no photos). Photos keep rotating through the night
 * window (the window only dims the screen), so the header's photo peek works at any hour.
 *
 * The photos shown make a reel: the last [HISTORY_MAX] names, with a cursor on the current one. [step] moves
 * the cursor (the peek's back and forward buttons): back retraces the reel, and forward past its end deals
 * new names from the shuffle. Rotation deals from the cursor too, dropping anything ahead of it. Only the
 * names are kept, so a step back fetches its photo again.
 *
 * Both variants are fetched and decoded before a photo is emitted, so the backdrop never swaps to a
 * half-loaded pair. A file that fails keeps the current photo and retries after a backoff of 1 to 5 min.
 * Decoding runs on [work], off the main thread; tests pass their own context.
 */
class BackdropLoader(
    private val source: HubSource,
    private val decoder: PhotoDecoder,
    random: Random = Random.Default,
    private val clock: () -> Long = System::currentTimeMillis,
    private val work: CoroutineContext = Dispatchers.Default,
) {
    private val _photo = MutableStateFlow<Photo?>(null)
    val photo: StateFlow<Photo?> = _photo.asStateFlow()

    private val bag = ShuffleBag<String>(random)

    /** The reel: names shown (or skipped over by a step), oldest first. Used only by the rotation coroutine. */
    private val reel = ArrayDeque<String>()

    /** The current photo's index in [reel], or -1 before the first. */
    private var pos = -1

    /** Pending steps from [step], taken by the rotation. */
    private val steps = Channel<Int>(Channel.UNLIMITED)

    /**
     * Moves [delta] photos along the reel: negative is back, positive forward. Taps that queue up while a
     * photo loads are summed, and only the photo they land on is fetched. Ignored while nothing rotates.
     */
    fun step(delta: Int) {
        steps.trySend(delta)
    }

    /**
     * Runs until cancelled. Each change of the effective settings restarts the rotation. While [hold] is
     * true (the peek), the timer never advances the photo by itself; steps still do.
     */
    @OptIn(ExperimentalCoroutinesApi::class)
    suspend fun run(settings: Flow<BgSettings?>, hold: StateFlow<Boolean> = MutableStateFlow(false)) {
        settings.map { s -> s?.takeIf { it.enabled } }
            .distinctUntilChanged()
            .collectLatest { s ->
                if (s == null) {
                    _photo.value = null
                    return@collectLatest
                }
                rotate(s, hold)
            }
    }

    private suspend fun rotate(s: BgSettings, hold: StateFlow<Boolean>): Nothing {
        val interval = s.intervalMs.coerceAtLeast(MIN_INTERVAL_MS)
        val rotation = Rotation()
        while (steps.tryReceive().isSuccess) Unit   // taps from while rotation was off
        var wait = rotation.advance(interval)
        while (true) {
            val delta = withTimeoutOrNull(wait) { steps.receive() }
            wait = when {
                delta != null -> {
                    var sum = delta
                    while (true) sum += steps.tryReceive().getOrNull() ?: break
                    browse(sum)
                    interval
                }
                hold.value -> wait   // peeking: re-arm, don't advance
                else -> rotation.advance(interval)
            }
        }
    }

    /** The timed rotation's list refresh and miss count. */
    private inner class Rotation {
        private var listedAt: Long? = null
        private var misses = 0

        /** Lists if due, deals and shows the next photo; returns how long to wait before the next one. */
        suspend fun advance(interval: Long): Long {
            val now = clock()
            val at = listedAt
            if (bag.isEmpty || at == null || now - at >= LIST_EVERY_MS) {
                when (val r = source.backgrounds()) {
                    is Fetch.Ok -> {
                        bag.reset(r.value)
                        listedAt = now
                        logEvent("bg_list", "n=${r.value.size}")
                    }
                    else -> logEvent("bg_list_fail", "err=${r.describe()}")   // keep the names we had
                }
            }
            val name = bag.next()
            val next = name?.let { load(it) }
            when {
                next != null -> {
                    while (reel.size > pos + 1) reel.removeLast()   // rotation drops what's ahead of the cursor
                    append(name)
                    pos = reel.lastIndex
                    _photo.value = next
                    misses = 0
                    logEvent("bg_photo", "name=$name luma=${"%.2f".format(next.luma)}")
                }
                bag.isEmpty -> _photo.value = null
                else -> {
                    misses++
                    logEvent("bg_miss", "name=$name n=$misses")
                }
            }
            return if (next != null) interval else BACKOFF_MS * misses.coerceIn(1, 5)
        }
    }

    /**
     * Moves the cursor [delta] along the reel, clamped at its oldest end; past the newest end it deals new
     * names. Shows the photo it lands on, or, if that fails, drops it from the reel and keeps the current one.
     */
    private suspend fun browse(delta: Int) {
        var target = (pos + delta).coerceAtLeast(0)
        while (target > reel.lastIndex) {
            val dealt = bag.next() ?: return
            if (append(dealt)) target--
        }
        if (target == pos) return
        val name = reel[target]
        val next = load(name)
        if (next == null) {
            reel.removeAt(target)
            if (target < pos) pos--
            logEvent("bg_step_miss", "d=$delta name=$name")
            return
        }
        pos = target
        _photo.value = next
        logEvent("bg_step", "d=$delta name=$name luma=${"%.2f".format(next.luma)}")
    }

    /** Appends [name] to the reel, dropping the oldest past [HISTORY_MAX]; true if it dropped one. */
    private fun append(name: String): Boolean {
        reel.addLast(name)
        if (reel.size <= HISTORY_MAX) return false
        reel.removeFirst()
        pos--
        return true
    }

    /** Both variants, or null. Sources don't throw; the decode is guarded, out-of-memory included. */
    private suspend fun load(name: String): Photo? {
        val sharpBytes = (source.background(name, 1024, 600, "cover", 0) as? Fetch.Ok)?.value ?: return null
        val softBytes = (source.background(name, 256, 150, "cover", SOFT_BLUR) as? Fetch.Ok)?.value ?: return null
        return withContext(work) {
            try {
                val (soft, luma) = decoder.soft(softBytes) ?: return@withContext null
                val sharp = decoder.sharp(sharpBytes) ?: return@withContext null
                Photo(sharp, soft, luma)
            } catch (e: Exception) {
                null
            } catch (e: OutOfMemoryError) {
                null
            }
        }
    }

    companion object {
        const val LIST_EVERY_MS = 10 * 60_000L
        const val MIN_INTERVAL_MS = 60_000L
        const val BACKOFF_MS = 60_000L
        const val SOFT_BLUR = 8
        const val HISTORY_MAX = 20
    }
}
