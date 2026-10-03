package io.haku.tablet.ui.backdrop

import io.haku.tablet.data.Fetch
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.describe
import io.haku.tablet.ui.logEvent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import kotlin.coroutines.CoroutineContext
import kotlin.random.Random

/** The config's `background` block, as the loader needs it. */
data class BgSettings(val enabled: Boolean, val intervalMs: Long)

/**
 * Rotates the NAS photos behind the cards. [photo] is the current one, or null for the plain gradient
 * (no config yet, backgrounds disabled, or an empty NAS folder). Photos keep rotating through the night
 * window (v3: the window only dims the screen), so the header's photo peek works at any hour.
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

    /** Runs until cancelled. Each change of the effective settings restarts the rotation. */
    @OptIn(ExperimentalCoroutinesApi::class)
    suspend fun run(settings: Flow<BgSettings?>) {
        settings.map { s -> s?.takeIf { it.enabled } }
            .distinctUntilChanged()
            .collectLatest { s ->
                if (s == null) {
                    _photo.value = null
                    return@collectLatest
                }
                rotate(s)
            }
    }

    private suspend fun rotate(s: BgSettings): Nothing {
        var listedAt: Long? = null
        var misses = 0
        while (true) {
            val now = clock()
            if (bag.isEmpty || listedAt == null || now - listedAt >= LIST_EVERY_MS) {
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
            delay(if (next != null) s.intervalMs.coerceAtLeast(MIN_INTERVAL_MS) else BACKOFF_MS * misses.coerceIn(1, 5))
        }
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
    }
}
