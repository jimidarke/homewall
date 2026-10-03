package io.haku.tablet.ui.cards

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.haku.tablet.data.Machine
import io.haku.tablet.ui.glyph.Glyph
import io.haku.tablet.ui.glyph.Glyphs
import io.haku.tablet.ui.model.LaundryModel
import io.haku.tablet.ui.text.FitText
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import io.haku.tablet.ui.theme.accentFor
import io.haku.tablet.ui.theme.parseColor
import kotlinx.coroutines.delay
import kotlin.math.max

/** At this card width the machines sit side by side (a 2-wide tile); below it they stack (1×1). */
private val SideBySideWidth = 400.dp
private val ColumnGap = 20.dp

private val BarHeight = 10.dp
private val SegmentGap = 6.dp
private val SegmentRadius = 3.dp

/** A machine: its status line, then the LED bar, with a wider gap to the next machine than within it. */
private val LineHeight = 24.dp
private val LineToBar = 6.dp
private val MachineHeight = LineHeight + LineToBar + BarHeight
private val MachineGap = 12.dp
private val MachineGlyph = 24.dp
private val LabelMax = 96.dp

/** Glyph to label, label to status: tight, so "running 25m long" still fits a 1×1 line at 16 sp. */
private val LineGap = 6.dp

private val Status = HakuType.state.copy(fontSize = 20.sp)
private val StatusMin = 16.sp

/** Unlit segments keep this much of the bar's colour, so the bar's shape always shows. */
private const val UNLIT = 0.08f

/**
 * One row per machine: its glyph in the machine's colour, its label and status, and under them the
 * on-screen LED bar (DESIGN 4.4). Rows stack on a 1×1 tile and sit side by side on a card 400 dp or wider.
 * With no machines it shows the summary tile instead. While the app is offline or the whole card is
 * stale, the bars hold still ([ledAnimates]).
 */
@Composable
fun LaundryCard(m: LaundryModel, modifier: Modifier = Modifier) {
    if (m.machines.isEmpty()) {
        ValueCard(m.base, modifier)
        return
    }
    val quiet = LocalOffline.current || m.base.stale
    GlassCard(m.base.chrome(), modifier) {
        BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
            val perRow = if (maxWidth >= SideBySideWidth) 2 else 1
            val fit = ((maxHeight + MachineGap) / (MachineHeight + MachineGap)).toInt()
            Column(verticalArrangement = Arrangement.spacedBy(MachineGap)) {
                m.machines.chunked(perRow).take(fit).forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(ColumnGap)) {
                        row.forEach { MachineRow(it, quiet, Modifier.weight(1f)) }
                        // A lone machine on a side-by-side row keeps its half width.
                        repeat(perRow - row.size) { Spacer(Modifier.weight(1f)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun MachineRow(machine: Machine, quiet: Boolean, modifier: Modifier) {
    val glyph = Glyphs.nameFor(machine.glyph, "laundry")
    val colour = parseColor(machine.color, fallback = accentFor(glyph))
    Column(modifier.height(MachineHeight)) {
        Row(Modifier.fillMaxWidth().height(LineHeight)) {
            Glyph(
                glyph, kind = "laundry", tint = if (machine.stale) Haku.offline else colour, size = MachineGlyph,
                modifier = Modifier.align(Alignment.CenterVertically),
            )
            Spacer(Modifier.width(LineGap))
            Text(
                machine.label, style = HakuType.sub, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.widthIn(max = LabelMax).alignByBaseline(),
            )
            Spacer(Modifier.width(LineGap))
            // The status gets the rest of the line, shrinking to fit before it ellipsizes ("running 25m long").
            Box(Modifier.weight(1f).alignByBaseline(), contentAlignment = Alignment.CenterEnd) {
                FitText(machine.status, style = Status, minSize = StatusMin, color = Haku.ink)
            }
        }
        Spacer(Modifier.height(LineToBar))
        LedBar(machine.mode, machine.leds, machine.stale, quiet, ledColorFor(machine.mode, machine.stale, colour))
    }
}

/**
 * Four equal segments, each the bar's [colour] at its [ledFrame] brightness. An animated mode steps a clock
 * at [ledStepMs] (never faster than 10 fps); the clock is read only while drawing, so a step redraws the bar
 * without recomposing or relaying out anything. Static modes, and every bar on a [quiet] card, run no clock
 * at all and draw the t = 0 frame.
 */
@Composable
private fun LedBar(mode: String, leds: Int, stale: Boolean, quiet: Boolean, colour: Color) {
    val t = remember { mutableLongStateOf(0L) }
    val animates = ledAnimates(mode, stale, quiet)
    if (animates) {
        LaunchedEffect(mode, stale) {
            val step = ledStepMs(if (stale) LED_STALE else mode) ?: return@LaunchedEffect
            t.longValue = 0L
            while (true) {
                delay(step)
                t.longValue += step
            }
        }
    }
    Spacer(
        Modifier.fillMaxWidth().height(BarHeight).drawWithCache {
            val gap = SegmentGap.toPx()
            val segment = Size((size.width - gap * (LED_SEGMENTS - 1)) / LED_SEGMENTS, size.height)
            val corner = CornerRadius(SegmentRadius.toPx())
            onDrawBehind {
                val frame = ledFrame(mode, leds, if (animates) t.longValue else 0L, stale)
                for (i in 0 until LED_SEGMENTS) {
                    drawRoundRect(
                        colour,
                        topLeft = Offset(i * (segment.width + gap), 0f),
                        size = segment,
                        cornerRadius = corner,
                        alpha = max(frame[i], UNLIT),
                    )
                }
            }
        },
    )
}
