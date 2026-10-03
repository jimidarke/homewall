package io.haku.tablet.ui.model

import io.haku.tablet.ui.formatTime
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * Keeps a value card's last good reading up while its source is out (the water meter drops off WiFi for
 * minutes at a time). Each value card that arrives fresh is remembered with the wall time of that poll. One
 * that arrives stale is replaced by the remembered copy. For the first [graceMs] after that reading the copy
 * shows as it was, so a source that blips for a minute or two never greys its card or turns the header
 * "degraded". Past the grace it is greyed: `stale`, no accent or alert, no ring, and "as of 7:41 PM" in
 * place of its detail line. Either way the live card's `pulseSeq` is kept, so the hold never replays a pulse.
 *
 * A held copy lasts until its module recovers, which replaces it, or until local midnight: yesterday's
 * reading is no reading for today, so the stale card then shows as the sidecar sent it. Only [ValueModel]
 * cards are held. Doors, laundry and agenda cards always show what they got, since a door's last state
 * is no stand-in for its current one; so does a doors or laundry module that fell back to a value tile.
 *
 * Pure apart from its memory, so it runs inside the poll on [PollTracker]'s thread. [zone] is the house's
 * own unless a test pins it.
 */
/**
 * How long a held reading shows as live before it greys. The water meter's WiFi drops for one to three
 * minutes at a time, several times an hour; only an outage longer than this is worth a grey card and a
 * "degraded" header.
 */
const val HOLD_GRACE_MS = 5 * 60_000L

class TileHold(
    private val zone: ZoneId = ZoneId.systemDefault(),
    private val graceMs: Long = HOLD_GRACE_MS,
) {
    private class Held(val card: ValueModel, val atMs: Long)

    /** Per module id, its last fresh value card. */
    private val held = HashMap<String, Held>()

    /**
     * One good poll's [cards], keyed by module id, with each stale value card standing in for its held copy
     * where there is one from today. [nowMs] is the poll's wall time. Ids missing from [cards] (gone in a
     * config reload) and cards that are no longer value cards are forgotten.
     */
    fun apply(cards: Map<String, CardModel>, nowMs: Long): Map<String, CardModel> {
        held.keys.retainAll { holdable(cards[it]) }
        return cards.mapValues { (id, card) ->
            if (card !is ValueModel || card.kind in NEVER_HELD) return@mapValues card
            if (!card.stale) {
                held[id] = Held(card, nowMs)
                return@mapValues card
            }
            val h = held[id] ?: return@mapValues card
            if (day(h.atMs) != day(nowMs)) {
                held.remove(id)
                return@mapValues card
            }
            if (nowMs - h.atMs in 0 until graceMs) {
                return@mapValues h.card.copy(kind = card.kind, title = card.title, pulseSeq = card.pulseSeq, pulseCount = 0)
            }
            h.card.copy(
                kind = card.kind,
                title = card.title,
                stale = true,
                active = false,
                alert = false,
                pulseSeq = card.pulseSeq,
                pulseCount = 0,
                asOf = "as of ${formatTime(h.atMs, zone)}",
            )
        }
    }

    private fun day(ms: Long): LocalDate = Instant.ofEpochMilli(ms).atZone(zone).toLocalDate()

    private fun holdable(card: CardModel?): Boolean = card is ValueModel && card.kind !in NEVER_HELD

    private companion object {
        /** Kinds whose last state is no stand-in for the current one, even as a plain value tile. */
        val NEVER_HELD = setOf("doors", "laundry")
    }
}
