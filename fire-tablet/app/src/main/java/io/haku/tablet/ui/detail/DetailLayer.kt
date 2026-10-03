package io.haku.tablet.ui.detail

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.AnimationVector1D
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.haku.tablet.data.HubConfig
import io.haku.tablet.ui.GAP_DP
import io.haku.tablet.ui.GridArea
import io.haku.tablet.ui.HEADER_DP
import io.haku.tablet.ui.MARGIN_DP
import io.haku.tablet.ui.TileRect
import io.haku.tablet.ui.backdrop.LocalBackdrop
import io.haku.tablet.ui.cards.FrostOrigin
import io.haku.tablet.ui.cards.glass
import io.haku.tablet.ui.glyph.Glyphs
import io.haku.tablet.ui.model.AgendaModel
import io.haku.tablet.ui.model.CardModel
import io.haku.tablet.ui.model.DoorsModel
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.model.ValueModel
import io.haku.tablet.ui.text.FitText
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import kotlinx.coroutines.flow.StateFlow

private val PanelRadius = 20.dp
private val PadH = 20.dp
private val PadTop = 14.dp
private val PadBottom = 16.dp
private val HeaderRow = 48.dp
private val HeaderGlyph = 30.dp
private val BigHeroMin = 30.sp

/** The gap between the header row and the body. */
private val HeaderGap = 8.dp

/** The body's height in a panel [panelDp] tall: what is left under the padding, the header row and its gap. */
internal fun detailBodyDp(panelDp: Float): Float = panelDp - (PadTop + PadBottom + HeaderRow + HeaderGap).value

/**
 * The open detail panel, over the card grid. The only reader of [detail], so a refresh or an open never
 * recomposes the dashboard. [reveal] (0 closed, 1 open) is shared with the grid, which fades out as the panel
 * grows (`alpha = 1 - reveal`, in its draw), so nothing shows through the panel's glass at night, when there
 * is no photo to frost.
 *
 * The panel is placed once, at its final rect (the grid area, [detailRect]), so its frost lines up from the
 * first frame; the reveal only clips it, growing from the tapped card's rect ([lerpRect]) in the draw phase.
 * It keeps the last panel it showed until the close animation ends. A tap anywhere on it closes it, except
 * while it is animating.
 */
@Composable
fun DetailLayer(
    detail: StateFlow<DetailUi?>,
    config: HubConfig,
    cards: Map<String, CardModel>,
    reveal: Animatable<Float, AnimationVector1D>,
    onClose: () -> Unit,
) {
    val open by detail.collectAsStateWithLifecycle()
    var shown by remember { mutableStateOf<DetailUi?>(null) }
    SideEffect { open?.let { shown = it } }
    val isOpen = open != null
    LaunchedEffect(isOpen) {
        val spec = tween<Float>(DETAIL_REVEAL_MS, easing = FastOutSlowInEasing)
        if (isOpen) {
            reveal.animateTo(1f, spec)
        } else {
            reveal.animateTo(0f, spec)
            shown = null
        }
    }
    val current = open ?: shown ?: return

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val area = GridArea(maxWidth.value, maxHeight.value, MARGIN_DP, HEADER_DP, MARGIN_DP, MARGIN_DP, GAP_DP)
        val full = detailRect(area)
        val module = config.modules.firstOrNull { it.id == current.id }
        val from = module?.let { io.haku.tablet.ui.tileRect(config.grid.cols, config.grid.rows, it.tile, area) } ?: full
        DetailPanel(current, cards[current.id], module?.title.orEmpty(), from, full, reveal, onClose)
    }
}

@Composable
private fun DetailPanel(
    ui: DetailUi,
    card: CardModel?,
    title: String,
    from: TileRect,
    full: TileRect,
    reveal: Animatable<Float, AnimationVector1D>,
    onClose: () -> Unit,
) {
    val backdrop = LocalBackdrop.current
    val origin = remember { FrostOrigin() }
    val clip = remember { Path() }
    Box(
        Modifier
            .offset(full.x.dp, full.y.dp)
            .size(full.w.dp, full.h.dp)
            .drawWithContent {
                val t = reveal.value
                if (t <= 0f) return@drawWithContent
                val r = lerpRect(from, full, t)
                val left = (r.x - full.x).dp.toPx()
                val top = (r.y - full.y).dp.toPx()
                clip.reset()
                clip.addRoundRect(
                    RoundRect(left, top, left + r.w.dp.toPx(), top + r.h.dp.toPx(), CornerRadius(PanelRadius.toPx())),
                )
                clipPath(clip) { this@drawWithContent.drawContent() }
            }
            .glass(backdrop, origin, PanelRadius)
            .clickable(interactionSource = null, indication = null) { if (!reveal.isRunning) onClose() },
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .graphicsLayer {
                    alpha = detailContentAlpha(reveal.value)
                    compositingStrategy = CompositingStrategy.ModulateAlpha
                }
                .padding(start = PadH, end = PadH, top = PadTop, bottom = PadBottom),
        ) {
            PanelHeader(title.ifEmpty { card?.title().orEmpty() }, card)
            Spacer(Modifier.height(HeaderGap))
            val body = Modifier.fillMaxWidth().weight(1f)
            when (val content = ui.content) {
                is DetailContent.Loaded -> DetailBody(content.detail, body)
                DetailContent.Local ->
                    if (card is AgendaModel) AgendaDetail(card, body) else TileSummary(card, null, body)
                DetailContent.Loading -> TileSummary(card, "Loading…", body)
                is DetailContent.Unavailable -> TileSummary(card, content.note, body)
            }
        }
    }
}

/** The module's glyph and title, what the live card says about its freshness, and the close hint. */
@Composable
private fun PanelHeader(title: String, card: CardModel?) {
    val value = card?.summary()
    Row(Modifier.fillMaxWidth().height(HeaderRow), verticalAlignment = Alignment.CenterVertically) {
        val glyph = card?.let { Glyphs.resolve(it.glyph(), it.kind()) }
        if (glyph != null) {
            Icon(glyph, contentDescription = null, tint = Haku.inkMuted, modifier = Modifier.size(HeaderGlyph))
            Spacer(Modifier.width(12.dp))
        }
        Text(title, style = HakuType.state, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
        val asOf = value?.asOf
        if (asOf != null) {
            Spacer(Modifier.width(14.dp))
            Text("Live data unavailable · $asOf", style = HakuType.detail, color = Haku.amber, maxLines = 1)
        }
        Spacer(Modifier.weight(1f))
        Text("Tap to close", style = HakuType.detail, color = Haku.inkFaint, maxLines = 1)
    }
}

/** The live tile, big: what a card without a sidecar detail (or before it arrives) shows in the panel. */
@Composable
private fun TileSummary(card: CardModel?, note: String?, modifier: Modifier) {
    val v = card?.summary()
    Column(modifier, verticalArrangement = Arrangement.Center) {
        if (v != null) SummaryLines(v)
        if (note != null) {
            Spacer(Modifier.height(16.dp))
            Text(note, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun ColumnScope.SummaryLines(v: ValueModel) {
    val alpha = if (v.stale) 0.5f else 1f
    FitText(
        v.hero, HakuType.hero.copy(fontSize = 64.sp, lineHeight = 64.sp), BigHeroMin, Haku.ink.copy(alpha = alpha),
        Modifier.fillMaxWidth(),
    )
    if (v.sub.isNotBlank()) Text(v.sub, style = HakuType.state, color = Haku.ink.copy(alpha = alpha), maxLines = 1)
    val detail = v.asOf ?: v.detail
    if (detail.isNotBlank()) Text(detail, style = HakuType.sub, color = Haku.inkMuted, maxLines = 1)
}

/** The summary tile behind any card: value cards are one, doors and laundry carry one as their base. */
private fun CardModel.summary(): ValueModel? = when (this) {
    is ValueModel -> this
    is DoorsModel -> base
    is LaundryModel -> base
    is AgendaModel -> null
}

private fun CardModel.title(): String = when (this) {
    is AgendaModel -> title
    else -> summary()?.title.orEmpty()
}

private fun CardModel.glyph(): String = when (this) {
    is AgendaModel -> glyph
    else -> summary()?.glyph.orEmpty()
}

private fun CardModel.kind(): String = when (this) {
    is AgendaModel -> kind
    else -> summary()?.kind.orEmpty()
}
