package io.haku.tablet.ui.model

import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubState

/**
 * A card that went from active to inactive less than this long ago doesn't ring again when it comes back
 * on. A meter flapping at a trickle (water at 0.0 <-> 0.4 L/min) would otherwise ring every few seconds.
 */
const val REPULSE_COOLDOWN_MS = 120_000L

/**
 * One good poll's cards, keyed by module id, and the titles of the modules whose card is stale (held or
 * not), in config order, for the header's "degraded" word. Agenda cards never count.
 */
data class PollResult(val cards: Map<String, CardModel>, val degraded: List<String>)

/**
 * Turns each good poll into cards, carrying the pulse and highlight baselines from one good
 * poll to the next. The baselines are the previous good poll's only: null at cold start and
 * after [onFail], so a gap re-baselines silently instead of pulsing.
 *
 * Each poll is projected once, then [hold] stands each value card's last good reading in for a stale one,
 * then the pulses are worked out from the held cards and stamped onto them. A held card is stale, so
 * entering or leaving a hold never rings ([pulses]). The hold outlives a failed poll.
 *
 * An ACTIVE pulse is held back while its card is inside [REPULSE_COOLDOWN_MS] of last going inactive;
 * ALERT pulses always ring. Only the ring is held back: the card's `active`, and so its accent, still
 * follows every poll. The cooldown is wall time ([onOk]'s `nowMs`), so it outlasts a failed poll.
 *
 * Not thread-safe: call it from one coroutine (the view model's poll loop). [onPulse] hears
 * each poll's fired pulses, when there are any.
 */
class PollTracker(
    private val hold: TileHold = TileHold(),
    private val onPulse: (Map<String, Pulse>) -> Unit = {},
) {
    private var prevSignals: Map<String, Signal>? = null

    /** Agenda id -> its newest item whenTs at the previous good poll. */
    private var highlightAfter: Map<String, Long?>? = null

    /** Per module id, bumped each time that card pulses. */
    private val pulseSeq = HashMap<String, Int>()

    /** Per module id, the wall time of the last good poll that found it newly inactive. */
    private val stoppedAt = HashMap<String, Long>()

    fun onOk(config: HubConfig, state: HubState, nowMs: Long): PollResult {
        val held = hold.apply(project(config, state, highlightAfter = highlightAfter.orEmpty()), nowMs)
        val sig = signals(held)
        val prev = prevSignals
        val fired = pulses(prev, sig).filter { (id, p) -> p == Pulse.ALERT || !coolingDown(id, nowMs) }
        if (prev != null) {
            for ((id, n) in sig) if (prev[id]?.active == true && !n.active) stoppedAt[id] = nowMs
        }
        for (id in fired.keys) pulseSeq[id] = (pulseSeq[id] ?: 0) + 1
        val cards = held.mapValues { (id, card) -> card.withPulse(pulseSeq[id] ?: 0, fired[id]) }
        prevSignals = sig
        highlightAfter = cards.values.filterIsInstance<AgendaModel>()
            .associate { a -> a.id to a.items.mapNotNull { it.whenTs }.maxOrNull() }
        if (fired.isNotEmpty()) onPulse(fired)
        return PollResult(cards, degraded(config, cards))
    }

    /** Re-baselines the pulses and highlights. The hold keeps its memory: a gap is no news about a reading. */
    fun onFail() {
        prevSignals = null
        highlightAfter = null
    }

    /** Inside the cooldown. A wall clock stepped back past the stop counts as outside it, never as a longer hold. */
    private fun coolingDown(id: String, nowMs: Long): Boolean {
        val stopped = stoppedAt[id] ?: return false
        return nowMs - stopped in 0 until REPULSE_COOLDOWN_MS
    }

    /** Titles of the stale value, doors and laundry cards, in config order; the id stands in for a blank title. */
    private fun degraded(config: HubConfig, cards: Map<String, CardModel>): List<String> =
        config.modules.filter { m ->
            when (val c = cards[m.id]) {
                is ValueModel -> c.stale
                is DoorsModel -> c.base.stale
                is LaundryModel -> c.base.stale
                is AgendaModel, null -> false
            }
        }.map { it.title.ifBlank { it.id } }
}
