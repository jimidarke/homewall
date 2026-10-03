package io.haku.tablet.ui.model

/** The part of a card that can pulse, compared between two consecutive good polls. */
data class Signal(val active: Boolean, val alert: Boolean, val stale: Boolean)

/** A one-shot ring: once when a card becomes active, twice when it becomes an alert. */
enum class Pulse { ACTIVE, ALERT }

/** How many times [pulse] rings: 2 for an alert, 1 for activating, 0 when this poll fired nothing. */
internal fun rings(pulse: Pulse?): Int = when (pulse) {
    Pulse.ALERT -> 2
    Pulse.ACTIVE -> 1
    null -> 0
}

/**
 * This card with its pulse: [seq] (bumped each time it has pulsed) and the rings of this poll's [pulse].
 * Doors and laundry carry it on their summary tile; agenda cards never pulse and come back as they are.
 */
internal fun CardModel.withPulse(seq: Int, pulse: Pulse?): CardModel = when (this) {
    is ValueModel -> copy(pulseSeq = seq, pulseCount = rings(pulse))
    is DoorsModel -> copy(base = base.copy(pulseSeq = seq, pulseCount = rings(pulse)))
    is LaundryModel -> copy(base = base.copy(pulseSeq = seq, pulseCount = rings(pulse)))
    is AgendaModel -> this
}

/** Value, doors and laundry cards (doors and laundry by their summary tile). Agenda cards never pulse. */
fun signals(cards: Map<String, CardModel>): Map<String, Signal> = buildMap {
    for ((id, card) in cards) {
        val v = when (card) {
            is ValueModel -> card
            is DoorsModel -> card.base
            is LaundryModel -> card.base
            is AgendaModel -> continue
        }
        put(id, Signal(v.active, v.alert, v.stale))
    }
}

/**
 * Rising edges from [prev] to [next]. An alert wins over activating in the same poll. [PollTracker] then
 * holds back an ACTIVE ring for a card that stopped less than [REPULSE_COOLDOWN_MS] ago.
 *
 * [prev] is null at cold start and after a failed poll, which re-baselines silently. An id
 * missing from [prev] (new since a config reload) never pulses, and neither does a card stale
 * on either side, so an HA or sidecar restart can't set off a pulse storm.
 */
fun pulses(prev: Map<String, Signal>?, next: Map<String, Signal>): Map<String, Pulse> {
    if (prev == null) return emptyMap()
    return buildMap {
        for ((id, n) in next) {
            val p = prev[id] ?: continue
            if (p.stale || n.stale) continue
            when {
                !p.alert && n.alert -> put(id, Pulse.ALERT)
                !p.active && n.active -> put(id, Pulse.ACTIVE)
            }
        }
    }
}
