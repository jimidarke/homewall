package io.haku.tablet.ui.cards

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.State
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorProducer
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.lerp
import io.haku.tablet.ui.backdrop.LocalBackdrop
import io.haku.tablet.ui.glyph.Glyphs
import io.haku.tablet.ui.motion.rememberPulse
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import kotlin.math.max
import kotlin.math.min

/**
 * Everything a [GlassCard] draws around its content. [glyph] is the name to show (falling back to the
 * [kind]'s default); [accent] colours the chip, rim and glow while [active]. [alert] adds the coral rim.
 * [stale] dims the content and drops the accent. A change of [pulseSeq] rings [pulseCount] times from the chip
 * ([rememberPulse]).
 */
@Immutable
data class CardChrome(
    val title: String,
    val glyph: String,
    val kind: String,
    val accent: Color,
    val active: Boolean,
    val alert: Boolean,
    val stale: Boolean,
    val pulseSeq: Int = 0,
    val pulseCount: Int = 0,
)

/**
 * How a card is coloured right now. [accent] is the card's held accent; [act] and [alert] are its animated
 * 0..1 levels. A card is lit while active **or** in alert, and an alert turns the tone coral whether or not
 * the card is active, so an idle alert card (energy over its threshold) gets a coral chip too.
 *
 * Every getter reads animated state: call them only inside a draw lambda.
 */
@Stable
class CardTone(val accent: Color, private val act: State<Float>, private val alert: State<Float>) {
    /** How strongly the card is coloured: the stronger of active and alert. */
    val lit: Float get() = max(act.value, alert.value)

    /** The colour it is coloured in: the accent, cross-fading to coral by alert. */
    val tone: Color get() = lerp(accent, Haku.coral, alert.value)

    /** [rest] (a muted ink) lit up toward [tone] by [lit]: glyph tints, level-bar fills. */
    fun over(rest: Color): Color = lerp(rest, tone, lit)

    /** The hero's colour: ink, cross-fading to coral by alert. A [ColorProducer], so it is read while drawing. */
    val hero: ColorProducer = ColorProducer { lerp(Haku.ink, Haku.coral, alert.value) }
}

/** The enclosing [GlassCard]'s [CardTone], for content that colours itself like the chip (the level bar). */
val LocalCardTone = staticCompositionLocalOf { CardTone(Haku.sage, Unlit, Unlit) }

/**
 * The alpha every card's content is held at, app-wide: 1, or down to 0.45 while the data is offline. A
 * `State` read only in the content's `graphicsLayer`, so dimming never recomposes a card. The glass (frost
 * and tint) never dims, so the sharp photo can't show through it.
 */
val LocalContentDim = staticCompositionLocalOf<State<Float>> { Undimmed }

/**
 * Whether the house data is offline, app-wide. Cards then go as quiet as stale ones: their accent, glow, rim
 * and alert coral fade out, since data at least 2 minutes old must not shout.
 */
val LocalOffline = compositionLocalOf { false }

private object Unlit : State<Float> {
    override val value = 0f
}

private object Undimmed : State<Float> {
    override val value = 1f
}

private val Radius = 20.dp
private val PadH = 14.dp
private val PadTop = 14.dp
private val PadBottom = 12.dp
private val HeaderRow = 48.dp
private val Chip = 48.dp
private val ChipRadius = 14.dp
private val ChipIcon = 30.dp

private const val ACTIVATE_MS = 600
private const val DEACTIVATE_MS = 1200
private const val ALERT_MS = 600

/** The ring pulse grows from the chip's edge out by [RingGrow], fading from [RING_ALPHA] to 0. */
private val RingStart = Chip / 2
private val RingGrow = 56.dp
private val RingWidth = 2.dp
private const val RING_ALPHA = 0.6f

/** The rim's accent alpha when fully active. */
private const val LIT_RIM_ALPHA = 0.85f

private const val STALE_ALPHA = 0.5f

/**
 * A card of smoked [glass]: the photo behind the card, frosted, under a night tint that follows the photo;
 * a glow and chip fill while lit, a rim that turns accent when active and coral on alert, and a 1 dp top
 * highlight. No shadows. An alert overrides active: it lights the glow, chip and glyph in coral, whether or not the
 * card is also active ([CardTone]). The header row holds the title and the glyph chip; [content] follows
 * below it.
 *
 * The activity and alert levels animate (600 ms in, 1,200 ms out), and a pulse rings out from the chip in
 * the accent, or coral on an alert. All of them are read only in draw lambdas, so they redraw the card
 * without recomposing it. Stale data and [LocalOffline] quiet the card (no accent, no alert); the content
 * dims for stale data and for [LocalContentDim]; the glass never does.
 */
@Composable
fun GlassCard(chrome: CardChrome, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val quiet = chrome.stale || LocalOffline.current
    val activeNow = chrome.active && !quiet
    val act = animateFloatAsState(
        targetValue = if (activeNow) 1f else 0f,
        animationSpec = tween(if (activeNow) ACTIVATE_MS else DEACTIVATE_MS),
        label = "act",
    )
    val alert = animateFloatAsState(
        targetValue = if (chrome.alert && !quiet) 1f else 0f,
        animationSpec = tween(ALERT_MS),
        label = "alert",
    )
    // Inactive glyphs often map to sage (water-outline, door-closed), so hold the last active accent: the
    // glow and rim then fade out in the colour they faded in with instead of snapping to sage first.
    val held = remember { HeldAccent(chrome.accent) }
    if (activeNow) held.color = chrome.accent
    val accent = held.color
    val tone = remember(accent, act, alert) { CardTone(accent, act, alert) }
    val ring = rememberPulse(chrome.pulseSeq, chrome.pulseCount)
    val ringColor = if (chrome.alert && !quiet) Haku.coral else accent
    val dim = LocalContentDim.current
    val backdrop = LocalBackdrop.current
    val origin = remember { FrostOrigin() }

    Box(
        modifier
            .glass(backdrop, origin, Radius)   // frost, tint, resting rim and highlight; the rest draws inside
            .drawWithCache {
                val radius = Radius.toPx()
                val chipCentre = Offset(size.width - (PadH + Chip / 2).toPx(), (PadTop + HeaderRow / 2).toPx())
                fun glowOf(c: Color) = Brush.radialGradient(
                    colors = listOf(c, c.copy(alpha = 0f)),
                    center = chipCentre,
                    radius = size.width * 0.7f,
                )
                val glow = glowOf(accent)
                val alertGlow = glowOf(Haku.coral)
                val ringStart = RingStart.toPx()
                val ringGrow = RingGrow.toPx()
                val ringStroke = Stroke(RingWidth.toPx())
                onDrawWithContent {
                    val a = act.value
                    val al = alert.value
                    val lit = tone.lit
                    if (lit > 0f) {
                        // The glow cross-fades from the accent to coral by alert, like the tone.
                        drawRect(glow, alpha = 0.18f * lit * (1f - al))
                        drawRect(alertGlow, alpha = 0.18f * lit * al)
                    }
                    val p = ring.value
                    if (p > 0f && p < 1f) {
                        drawCircle(
                            ringColor,
                            radius = ringStart + ringGrow * p,
                            center = chipCentre,
                            alpha = (1f - p) * RING_ALPHA,
                            style = ringStroke,
                        )
                    }
                    drawContent()

                    if (a > 0f || al > 0f) {
                        // Over the glass's resting rim: the accent (85%) fades in and thickens with activity,
                        // and coral takes over with alert. At rest nothing is drawn here.
                        val rimW = lerp(lerp(1.dp, 1.5.dp, a), 2.dp, al).toPx()
                        val rim = lerp(accent.copy(alpha = LIT_RIM_ALPHA * a), Haku.coral, al)
                        drawRoundRect(
                            color = rim,
                            topLeft = Offset(rimW / 2, rimW / 2),
                            size = Size(size.width - rimW, size.height - rimW),
                            cornerRadius = CornerRadius(radius - rimW / 2),
                            style = Stroke(rimW),
                        )
                    }
                }
            },
    ) {
        CompositionLocalProvider(LocalCardTone provides tone) {
            Column(
                Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        alpha = min(if (chrome.stale) STALE_ALPHA else 1f, dim.value)
                        // Alpha per draw call, not through an offscreen buffer: card content barely overlaps
                        // itself, and each dim (stale, offline) would otherwise render every card through a
                        // buffer that HWUI then keeps cached (measured +9 MB PSS on the Fire).
                        compositingStrategy = CompositingStrategy.ModulateAlpha
                    }
                    .padding(start = PadH, end = PadH, top = PadTop, bottom = PadBottom),
            ) {
                Row(Modifier.fillMaxWidth().height(HeaderRow), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        chrome.title,
                        style = HakuType.cardTitle,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    GlyphChip(chrome.glyph, chrome.kind, tone)
                }
                content()
            }
        }
    }
}

/** Not snapshot state: it only remembers a colour between compositions, it never triggers one. */
private class HeldAccent(var color: Color)

/** The 48 dp chip: its fill and glyph tint follow [tone], read in the draw phase. */
@Composable
private fun GlyphChip(glyph: String, kind: String, tone: CardTone) {
    val painter = Glyphs.resolve(glyph, kind)?.let { rememberVectorPainter(it) }
    Spacer(
        Modifier.size(Chip).drawWithCache {
            val corner = CornerRadius(ChipRadius.toPx())
            val icon = ChipIcon.toPx()
            val inset = (size.width - icon) / 2f
            onDrawBehind {
                val lit = tone.lit
                if (lit > 0f) drawRoundRect(tone.tone, cornerRadius = corner, alpha = 0.28f * lit)
                if (painter != null) {
                    translate(inset, inset) {
                        with(painter) {
                            draw(Size(icon, icon), colorFilter = ColorFilter.tint(tone.over(Haku.inkMuted)))
                        }
                    }
                }
            }
        },
    )
}
