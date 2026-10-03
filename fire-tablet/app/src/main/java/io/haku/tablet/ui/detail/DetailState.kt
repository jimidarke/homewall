package io.haku.tablet.ui.detail

import androidx.compose.runtime.Immutable
import io.haku.tablet.data.Detail
import io.haku.tablet.data.Fetch
import io.haku.tablet.ui.GridArea
import io.haku.tablet.ui.TileRect

/** What an open detail panel shows below its header. */
@Immutable
sealed interface DetailContent {
    /** The sidecar's detail is on its way; the panel shows the live tile, big, meanwhile. */
    data object Loading : DetailContent

    /** Calendar and Activity: the card's own items, laid out full width. Nothing to fetch. */
    data object Local : DetailContent

    data class Loaded(val detail: Detail) : DetailContent

    /** No sidecar detail for this card (404), or it failed: the live tile, big, with [note] under it if any. */
    data class Unavailable(val note: String?) : DetailContent
}

/** The open detail panel: which module ([id]) and what it shows. */
@Immutable
data class DetailUi(val id: String, val content: DetailContent)

/** The detail panel fills the card grid's whole area (below the header, inside the margins). */
fun detailRect(area: GridArea): TileRect =
    TileRect(area.left, area.top, area.width - area.left - area.right, area.height - area.top - area.bottom)

/** [from] grown toward [to] by [t] in 0..1: the visible part of the panel during its reveal. */
fun lerpRect(from: TileRect, to: TileRect, t: Float): TileRect {
    val k = t.coerceIn(0f, 1f)
    fun mix(a: Float, b: Float) = a + (b - a) * k
    return TileRect(mix(from.x, to.x), mix(from.y, to.y), mix(from.w, to.w), mix(from.h, to.h))
}

/** The panel's content fades in over the reveal's last [CONTENT_FADE_SPAN], so it never shows squeezed into the card. */
fun detailContentAlpha(reveal: Float): Float =
    ((reveal - (1f - CONTENT_FADE_SPAN)) / CONTENT_FADE_SPAN).coerceIn(0f, 1f)

const val CONTENT_FADE_SPAN = 0.6f

/** Reveal and close, each way (Contract v3 §3). */
const val DETAIL_REVEAL_MS = 250

/** An open panel refetches its detail this often, and closes itself after [DETAIL_AUTO_CLOSE_MS]. */
const val DETAIL_REFRESH_MS = 60_000L
const val DETAIL_AUTO_CLOSE_MS = 90_000L

/**
 * What a panel shows after a detail fetch. A detail replaces whatever was there; a 404 means the module has
 * none, so the tile shows big for good. Any other failure keeps an already loaded detail (the next refresh may
 * bring it back) and otherwise says the details couldn't load.
 */
fun nextDetailContent(current: DetailContent, fetch: Fetch<Detail>): DetailContent = when (fetch) {
    is Fetch.Ok -> DetailContent.Loaded(fetch.value)
    is Fetch.HttpError -> if (fetch.code == 404) DetailContent.Unavailable(null) else failed(current)
    else -> failed(current)
}

private fun failed(current: DetailContent): DetailContent =
    if (current is DetailContent.Loaded) current else DetailContent.Unavailable(DETAIL_FAILED_NOTE)

const val DETAIL_FAILED_NOTE = "Couldn't load the details. Trying again in a minute."

/** A module with no detail of its own stops refreshing: nothing will change until it is opened again. */
fun detailSettled(content: DetailContent): Boolean =
    content == DetailContent.Local || content == DetailContent.Unavailable(null)
