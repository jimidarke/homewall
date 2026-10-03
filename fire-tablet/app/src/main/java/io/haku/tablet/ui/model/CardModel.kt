package io.haku.tablet.ui.model

import androidx.compose.runtime.Immutable
import io.haku.tablet.data.AgendaItem
import io.haku.tablet.data.Door
import io.haku.tablet.data.Machine

/**
 * What one grid card shows, projected from config + state by [project]. Immutable, so an
 * unchanged card skips recomposition. [id] is the module id from /api/config.
 */
@Immutable
sealed interface CardModel {
    val id: String
}

/**
 * A summary tile. The strings are the sidecar's, as given. [alert] is severity `high`; [level]
 * is 0..100 or null. A pulse fires when [pulseSeq] changes, and rings [pulseCount] times
 * (1 on becoming active, 2 on becoming an alert, 0 when this poll fired nothing).
 *
 * [asOf] is set only on a held card ([TileHold]): the last good reading, shown stale, with
 * "as of 7:41 PM" in place of the detail line.
 */
@Immutable
data class ValueModel(
    override val id: String,
    val kind: String,
    val title: String,
    val glyph: String,
    val hero: String,
    val sub: String,
    val detail: String,
    val alert: Boolean,
    val active: Boolean,
    val level: Int?,
    val stale: Boolean,
    val pulseSeq: Int = 0,
    val pulseCount: Int = 0,
    val asOf: String? = null,
) : CardModel

/** A doors card: per-door rows plus the summary tile in [base]. */
@Immutable
data class DoorsModel(val base: ValueModel, val doors: List<Door>) : CardModel {
    override val id get() = base.id
}

/** A laundry card: per-machine rows plus the summary tile in [base]. */
@Immutable
data class LaundryModel(val base: ValueModel, val machines: List<Machine>) : CardModel {
    override val id get() = base.id
}

/**
 * A list card. [activity] marks the Activity feed (`tile.dropHeaders`). Items newer than
 * [highlightAfter] (epoch seconds) are new since the previous good poll; null highlights none.
 */
@Immutable
data class AgendaModel(
    override val id: String,
    val kind: String,
    val title: String,
    val glyph: String,
    val items: List<AgendaItem>,
    val activity: Boolean,
    val stale: Boolean,
    val highlightAfter: Long?,
) : CardModel
