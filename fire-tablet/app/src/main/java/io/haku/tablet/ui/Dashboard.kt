package io.haku.tablet.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.AnimatedVisibilityScope
import androidx.compose.animation.EnterExitState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.AnimationVector1D
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.haku.tablet.data.HubConfig
import io.haku.tablet.ui.backdrop.Backdrop
import io.haku.tablet.ui.backdrop.BackdropState
import io.haku.tablet.ui.backdrop.LocalBackdrop
import io.haku.tablet.ui.backdrop.Photo
import io.haku.tablet.ui.cards.CardFor
import io.haku.tablet.ui.cards.LocalContentDim
import io.haku.tablet.ui.cards.LocalOffline
import io.haku.tablet.ui.cards.placeholderCard
import io.haku.tablet.ui.detail.DetailLayer
import io.haku.tablet.ui.detail.DetailUi
import io.haku.tablet.ui.glyph.Glyph
import io.haku.tablet.ui.model.CardModel
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import io.haku.tablet.ui.theme.LockFontScale
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map

/** Offline: card content dims to this over [DIM_MS]; the glass stays opaque. */
private const val OFFLINE_DIM = 0.45f
private const val DIM_MS = 600

/** The photo peek's fade: the UI and the scrim out, or back in (v3 contract §3). */
private const val PEEK_FADE_MS = 400

/** The peek's back and forward buttons: a smoked-glass disc with a chevron, in a larger touch target. */
private val PeekTarget = 72.dp
private val PeekDisc = 56.dp
private val PeekChevron = 36.dp
private val PeekFill = Haku.night.copy(alpha = 0.45f)

/**
 * The whole screen, in layers: the photo backdrop, then the UI layer: the card grid (or a status screen
 * until the config arrives), the offline banner, and the header over the grid's top inset. The UI layer
 * steps ±2 dp every 10 min against burn-in ([rememberBurnInShift]); the backdrop stays put, and the frost
 * follows each card through `onPlaced`. Offline ([offlineShown]) dims the cards' content, quiets their
 * accents ([LocalOffline]) and slides up the banner.
 *
 * A header tap ([headerTapAction]) starts the photo peek ([peek], [onStartPeek]): the UI layer and the scrim
 * fade out over 400 ms through [BackdropState.veil], read only in draw, so the photo shows bare. While it
 * shows or fades, a full-screen catcher on top takes every tap and ends it ([onEndPeek]), and so does Back,
 * except the back and forward buttons over it ([PeekControls]), which step the photo ([onStepPhoto]).
 *
 * A card tap opens its detail panel ([onOpenDetail]), drawn over the grid by [DetailLayer], which alone reads
 * [detail]. A tap on the panel, a header tap or Back closes it ([onCloseDetail]).
 */
@Composable
fun Dashboard(
    ui: UiState,
    freshness: StateFlow<Freshness>,
    lastOkAt: StateFlow<Long?>,
    photo: StateFlow<Photo?>,
    night: StateFlow<Boolean>,
    peek: StateFlow<Boolean>,
    onStartPeek: () -> Unit,
    onEndPeek: () -> Unit,
    onStepPhoto: (Int) -> Unit,
    detail: StateFlow<DetailUi?>,
    onOpenDetail: (String) -> Unit,
    onCloseDetail: () -> Unit,
) {
    LockFontScale {
        val fresh by freshness.collectAsStateWithLifecycle()
        val peeking by peek.collectAsStateWithLifecycle()
        val offline = offlineShown(fresh, ui.stateFetched)
        val config = ui.config
        val backdrop = remember { BackdropState() }
        val dim = animateFloatAsState(if (offline) OFFLINE_DIM else 1f, tween(DIM_MS), label = "offlineDim")
        val shift = rememberBurnInShift()
        LaunchedEffect(peeking) { backdrop.veil.animateTo(if (peeking) 1f else 0f, tween(PEEK_FADE_MS)) }
        // From a peek's start until its fade back has finished. Derived, so it flips twice per peek and the
        // fade's frames never recompose.
        val veiled by remember(backdrop) { derivedStateOf { backdrop.veil.value > 0f } }
        // Open or closed only, so a panel's refresh never recomposes the screen; the panel reads the rest itself.
        val detailOpen by remember(detail) { detail.map { it != null }.distinctUntilChanged() }
            .collectAsStateWithLifecycle(initialValue = false)
        // 0 closed, 1 open: the panel's reveal, and the grid fading out under it. Read only in draw.
        val reveal = remember { Animatable(0f) }
        val act: (HeaderTap) -> Unit = { action ->
            when (action) {
                HeaderTap.CLOSE_DETAIL -> onCloseDetail()
                HeaderTap.END_PEEK -> onEndPeek()
                HeaderTap.START_PEEK -> onStartPeek()
                HeaderTap.NONE -> Unit
            }
        }
        CompositionLocalProvider(
            LocalBackdrop provides backdrop,
            LocalContentDim provides dim,
            LocalOffline provides offline,
        ) {
            Box(Modifier.fillMaxSize()) {
                PhotoBackdrop(photo, night, backdrop)
                Box(
                    Modifier
                        .fillMaxSize()
                        .offset { shift.value.toPx(this) }
                        .graphicsLayer {
                            alpha = 1f - backdrop.veil.value
                            // Alpha per draw call, not an offscreen buffer for the whole screen (see GlassCard).
                            compositingStrategy = CompositingStrategy.ModulateAlpha
                        },
                ) {
                    if (config == null) {
                        StatusScreen(ui)
                    } else {
                        Grid(config, ui.cards, reveal, onOpenDetail)
                        DetailLayer(detail, config, ui.cards, reveal, onCloseDetail)
                        AnimatedVisibility(
                            visible = offline,
                            modifier = Modifier.align(Alignment.BottomCenter),
                            enter = slideInVertically(Haku.spatialStandard()) { it },
                            exit = slideOutVertically(Haku.spatialStandard()) { it },
                            label = "offlineBanner",
                        ) {
                            OfflineBanner(lastOkAt, ui.error)
                        }
                    }
                    Header(fresh, ui.stateFetched, ui.degraded, onTap = {
                        act(headerTapAction(detail.value != null, peek.value, hasPhoto = photo.value != null))
                    })
                }
                if (peeking || veiled) {
                    TapCatcher(onEndPeek)
                    PeekControls(backdrop, onStepPhoto)
                }
            }
        }
        BackHandler(enabled = peeking || detailOpen) {
            act(headerTapAction(detailOpen, peek.value, hasPhoto = false))
        }
    }
}

/** Takes every tap on the screen, with no feedback. Last in its box, so nothing under it sees the tap. */
@Composable
private fun TapCatcher(onTap: () -> Unit) {
    Spacer(Modifier.fillMaxSize().clickable(interactionSource = null, indication = null, onClick = onTap))
}

/**
 * The peek's back (‹, -1) and forward (›, +1) buttons, centred on the left and right edges over the
 * [TapCatcher]. They fade in and out with the peek ([BackdropState.veil], read in draw); a tap elsewhere
 * falls through to the catcher. A tap during the fade back is ignored by the view model.
 */
@Composable
private fun PeekControls(backdrop: BackdropState, onStep: (Int) -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .padding(horizontal = MARGIN_DP.dp)
            .graphicsLayer {
                alpha = backdrop.veil.value
                compositingStrategy = CompositingStrategy.ModulateAlpha
            },
    ) {
        PeekButton("chevron-left", Modifier.align(Alignment.CenterStart)) { onStep(-1) }
        PeekButton("chevron-right", Modifier.align(Alignment.CenterEnd)) { onStep(+1) }
    }
}

@Composable
private fun PeekButton(glyph: String, modifier: Modifier, onTap: () -> Unit) {
    Box(
        modifier
            .size(PeekTarget)
            .clickable(interactionSource = null, indication = null, onClick = onTap),
        contentAlignment = Alignment.Center,
    ) {
        Box(Modifier.size(PeekDisc).background(PeekFill, CircleShape), contentAlignment = Alignment.Center) {
            Glyph(glyph, kind = "", tint = Haku.ink, size = PeekChevron)
        }
    }
}

/** Read here, not in [Dashboard], so a new photo only restarts the backdrop's cross-fade. */
@Composable
private fun PhotoBackdrop(photo: StateFlow<Photo?>, night: StateFlow<Boolean>, state: BackdropState) {
    val current by photo.collectAsStateWithLifecycle()
    val isNight by night.collectAsStateWithLifecycle()
    Backdrop(current, state, isNight)
}

/**
 * Cards placed in root coordinates on the config's grid, inset below the header. A module with no card
 * yet shows a placeholder instead of leaving a hole. A tap on a card opens its detail panel ([onOpen]); the
 * grid fades out as the panel grows over it ([reveal], read in draw).
 */
@Composable
private fun Grid(
    config: HubConfig,
    cards: Map<String, CardModel>,
    reveal: Animatable<Float, AnimationVector1D>,
    onOpen: (String) -> Unit,
) {
    BoxWithConstraints(
        Modifier
            .fillMaxSize()
            .graphicsLayer {
                alpha = 1f - reveal.value
                compositingStrategy = CompositingStrategy.ModulateAlpha
            },
    ) {
        val area = GridArea(maxWidth.value, maxHeight.value, MARGIN_DP, HEADER_DP, MARGIN_DP, MARGIN_DP, GAP_DP)
        config.modules.forEach { m ->
            key(m.id) {
                val r = tileRect(config.grid.cols, config.grid.rows, m.tile, area)
                val cell = Modifier
                    .offset(r.x.dp, r.y.dp)
                    .size(r.w.dp, r.h.dp)
                    .clickable(interactionSource = null, indication = null) { onOpen(m.id) }
                CardFor(cards[m.id] ?: placeholderCard(m), cell)
            }
        }
    }
}

/** "No data since 9:41 PM · <error>", or "No data yet" before any good poll. */
internal fun bannerText(lastOk: Long?, error: String?): String {
    val since = lastOk?.let { "No data since ${formatTime(it)}" } ?: "No data yet"
    return listOfNotNull(since, error).joinToString(" · ")
}

/**
 * The offline banner ([bannerText]). It keeps its offline text while it slides out on recovery, since the
 * poll that ended the outage has already replaced the time and cleared the error. [lastOkAt] is read here,
 * not in [Dashboard], so the 5 s poll heartbeat never recomposes the whole screen.
 */
@Composable
private fun AnimatedVisibilityScope.OfflineBanner(lastOkAt: StateFlow<Long?>, error: String?) {
    val lastOk by lastOkAt.collectAsStateWithLifecycle()
    val held = remember { HeldText() }
    if (transition.targetState == EnterExitState.Visible) held.text = bannerText(lastOk, error)
    Text(
        held.text,
        style = HakuType.sub,
        color = Haku.ink,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
        modifier = Modifier
            .padding(16.dp)
            .background(Haku.offline, RoundedCornerShape(14.dp))
            .padding(horizontal = 18.dp, vertical = 10.dp),
    )
}

/** Not snapshot state: it only carries the banner's text from one composition to the next. */
private class HeldText(var text: String = "")

/** Before the first config: connecting, or why it failed. Both name the sidecar being tried. */
@Composable
private fun StatusScreen(ui: UiState) {
    Column(
        Modifier.fillMaxSize().padding(top = HEADER_DP.dp, start = 48.dp, end = 48.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        val error = ui.error
        Text(
            if (error == null) "Connecting to HAku" else "Can't reach HAku",
            style = HakuType.state,
            color = Haku.ink,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(10.dp))
        Text(ui.sidecar, style = HakuType.sub, color = Haku.inkMuted, textAlign = TextAlign.Center)
        if (error != null) {
            Spacer(Modifier.height(6.dp))
            Text(error, style = HakuType.detail, color = Haku.inkMuted, textAlign = TextAlign.Center)
        }
    }
}
