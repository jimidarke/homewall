package io.haku.tablet.ui.model

import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubState
import io.haku.tablet.data.ModuleDesc

/**
 * One card per module, keyed by module id, with state read by the module's feed key. Pure, so
 * the view model can run it off the main thread on every poll.
 *
 * [pulseSeq] and [pulseKind] come from [pulses] (per module id); [highlightAfter] is, per agenda
 * id, the newest item time seen at the previous good poll.
 */
fun project(
    config: HubConfig,
    state: HubState,
    pulseSeq: Map<String, Int> = emptyMap(),
    pulseKind: Map<String, Pulse> = emptyMap(),
    highlightAfter: Map<String, Long?> = emptyMap(),
): Map<String, CardModel> = config.modules.associate { m ->
    m.id to card(m, state, pulseSeq[m.id] ?: 0, pulseKind[m.id], highlightAfter[m.id])
}

/**
 * Doors and laundry need their arrays, else they fall back to a value tile like any other
 * module. Anything that isn't an agenda, including an unknown `tile.type`, is a value tile
 * (the Roku's hkModuleKind rule).
 */
private fun card(m: ModuleDesc, state: HubState, seq: Int, pulse: Pulse?, highlightAfter: Long?): CardModel {
    if (m.kind == "doors") state.doors(m.key)?.let { return DoorsModel(value(m, state, seq, pulse), it) }
    if (m.kind == "laundry") state.laundry(m.key)?.let { return LaundryModel(value(m, state, seq, pulse), it) }
    if (m.tile.type == "agenda") {
        return AgendaModel(
            id = m.id,
            kind = m.kind,
            title = m.title,
            glyph = state.tile(m.key)?.glyph.orEmpty(),
            items = state.items(m.key, m.tile.dropHeaders),
            activity = m.tile.dropHeaders,
            stale = state.stale(m.key),
            highlightAfter = highlightAfter,
        )
    }
    return value(m, state, seq, pulse)
}

/**
 * The module's tile as given; no tile block, or a blank hero, shows a dash. It is stale when the sidecar
 * says so, and also when it has no tile, a blank hero or an `error`: none of those is a reading, so
 * [TileHold] can stand the last good one in for it.
 */
private fun value(m: ModuleDesc, state: HubState, seq: Int, pulse: Pulse?): ValueModel {
    val t = state.tile(m.key)
    val hero = t?.hero?.takeIf { it.isNotBlank() }
    return ValueModel(
        id = m.id,
        kind = m.kind,
        title = m.title,
        glyph = t?.glyph.orEmpty(),
        hero = hero ?: "—",
        sub = t?.sub.orEmpty(),
        detail = t?.detail.orEmpty(),
        alert = t?.severity == "high",
        active = t?.active ?: false,
        level = t?.level,
        stale = state.stale(m.key) || hero == null || state.error(m.key) != null,
        pulseSeq = seq,
        pulseCount = rings(pulse),
    )
}
