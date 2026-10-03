package io.haku.tablet.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType

/** Left and right inset of the header: the grid margin plus a card's content padding, so the clock lines up with card text. */
private val HeaderInset = 26.dp

/** The header names up to this many degraded modules; from one more on, it counts them instead. */
private const val DEGRADED_NAMES_MAX = 2

/** The header's freshness word and the colour of the dot beside it. */
internal data class HeaderStatus(val label: String, val dot: Color)

/**
 * "connecting" until the first state fetch has finished: freshness reads OFFLINE before any poll, and the
 * wall shouldn't say offline before it has tried. The dot is the palette's neutral grey for unknown states.
 * After that, offline (grey) or lagging (amber) if the data itself is old; otherwise "degraded" (amber) while
 * any module's card is stale ([degraded], titles in config order: "degraded · Water", "degraded · Water, Gas",
 * "degraded · 3" from three on), else live (sage).
 */
internal fun headerStatus(fresh: Freshness, stateFetched: Boolean, degraded: List<String>): HeaderStatus = when {
    !stateFetched -> HeaderStatus("connecting", Haku.offline)
    fresh == Freshness.OFFLINE -> HeaderStatus("offline", Haku.offline)
    fresh == Freshness.LAGGING -> HeaderStatus("lagging", Haku.amber)
    degraded.isNotEmpty() -> HeaderStatus("degraded · ${degradedNames(degraded)}", Haku.amber)
    else -> HeaderStatus("live", Haku.sage)
}

private fun degradedNames(titles: List<String>): String =
    if (titles.size > DEGRADED_NAMES_MAX) titles.size.toString() else titles.joinToString(", ")

/** What a tap on the header does ([headerTapAction]). */
enum class HeaderTap { CLOSE_DETAIL, END_PEEK, START_PEEK, NONE }

/**
 * A header tap closes an open detail panel first, else ends a photo peek, else starts one when there is a
 * photo to show; with none of those it does nothing. Back asks the same with [hasPhoto] false, so it closes
 * whatever is open and never starts a peek.
 */
fun headerTapAction(detailOpen: Boolean, peeking: Boolean, hasPhoto: Boolean): HeaderTap = when {
    detailOpen -> HeaderTap.CLOSE_DETAIL
    peeking -> HeaderTap.END_PEEK
    hasPhoto -> HeaderTap.START_PEEK
    else -> HeaderTap.NONE
}

/**
 * The top band: clock and date on the left, the data-freshness dot and word ([headerStatus]) on the right.
 * The whole band is one tap target ([onTap], decided by [headerTapAction]), with no ripple or other touch
 * feedback: the wall answers a tap only by what the tap does.
 */
@Composable
fun Header(
    fresh: Freshness,
    stateFetched: Boolean,
    degraded: List<String>,
    onTap: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .fillMaxWidth()
            .height(HEADER_DP.dp)
            .clickable(interactionSource = null, indication = null, onClick = onTap)
            .padding(horizontal = HeaderInset),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Clock()
        Spacer(Modifier.weight(1f))
        val status = headerStatus(fresh, stateFetched, degraded)
        Box(Modifier.size(10.dp).background(status.dot, CircleShape))
        Spacer(Modifier.width(8.dp))
        Text(status.label, style = HakuType.detail, color = Haku.inkMuted)
    }
}
