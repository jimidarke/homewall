package io.haku.tablet.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.haku.tablet.data.DetailBlock
import io.haku.tablet.data.ForecastDay
import io.haku.tablet.data.HourCell
import io.haku.tablet.ui.glyph.Glyph
import io.haku.tablet.ui.text.FitText
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType

/*
 * The weather panel's own blocks: the `now` hero, the compact outlook and the `hourly` strip. Heights are fixed
 * (in dp, as constants) so a column can count what fits before composing anything, like the `rows` blocks do;
 * DetailBlocksTest checks that six facts still fit between the hero and three outlook days.
 */

/** The hero is a glyph row ([NOW_HERO_DP]) and a line for the high/low and freshness ([NOW_META_DP]). */
private const val NOW_HERO_DP = 92f
private const val NOW_META_DP = 24f
internal const val NOW_DP = NOW_HERO_DP + NOW_META_DP

/** One day of the outlook: weekday, glyph, condition, "hi / lo", rain chance. */
internal const val OUTLOOK_ROW_DP = 32f

/** The hourly strip: label, glyph, temperature, rain chance. Cells are 1/[HOURLY_SLOTS] of its width, whatever the count up to that. */
internal const val HOURLY_DP = 112f
private const val HOURLY_SLOTS = 8

private val NowGlyph = 72.dp
private val OutlookGlyph = 28.dp
private val HourGlyph = 32.dp
private val NowTempSize = 56.sp
private val FitMin = 16.sp

/**
 * The hero: the condition glyph and the temperature at 56 sp with the condition under it, then the high/low at
 * the left and the "Updated" time at the right of one line. The glyph is left out when the sidecar sent none.
 */
@Composable
internal fun NowBlock(now: DetailBlock.Now, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().height(NOW_DP.dp)) {
        Row(Modifier.fillMaxWidth().height(NOW_HERO_DP.dp), verticalAlignment = Alignment.CenterVertically) {
            if (now.glyph != null) {
                Glyph(now.glyph, kind = "weather", tint = Haku.ink, size = NowGlyph)
                Spacer(Modifier.width(12.dp))
            }
            // The 56 sp temperature line measures nearer 68 dp, so let this column be as tall as it wants (centred in
            // the row) instead of squeezing the condition into what the temperature leaves.
            Column(Modifier.weight(1f).wrapContentHeight(align = Alignment.CenterVertically, unbounded = true)) {
                FitText(
                    now.temp, HakuType.hero.copy(fontSize = NowTempSize, lineHeight = NowTempSize), FitMin, Haku.ink,
                    Modifier.fillMaxWidth(),
                )
                if (now.cond != null) {
                    Text(now.cond, style = HakuType.sub, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        Row(Modifier.fillMaxWidth().height(NOW_META_DP.dp), verticalAlignment = Alignment.CenterVertically) {
            if (now.hilo != null) {
                Text(now.hilo, style = HakuType.sub, color = Haku.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Spacer(Modifier.weight(1f))
            if (now.sub != null) {
                Text(now.sub, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** One line a day: weekday, a 28 dp glyph, the condition (shrinks first), "hi / lo" and the rain chance at the right. */
@Composable
internal fun OutlookBlock(days: List<ForecastDay>, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth()) {
        for (day in days) {
            Row(Modifier.fillMaxWidth().height(OUTLOOK_ROW_DP.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(day.label, style = HakuType.agendaTitle, color = Haku.ink, maxLines = 1, modifier = Modifier.width(48.dp))
                Glyph(day.glyph, kind = "weather", tint = Haku.ink, size = OutlookGlyph)
                Spacer(Modifier.width(10.dp))
                Text(
                    day.cond, style = HakuType.agendaTitle, color = Haku.inkMuted, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                )
                Text(
                    hiLo(day.hi, day.lo).orEmpty(), style = HakuType.agendaTitle, color = Haku.ink, maxLines = 1,
                    textAlign = TextAlign.End, modifier = Modifier.widthIn(min = 84.dp),
                )
                Box(Modifier.width(48.dp), contentAlignment = Alignment.CenterEnd) {
                    if (day.sub != null) {
                        Text(day.sub, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1)
                    }
                }
            }
        }
    }
}

/** Up to 12 cells in equal slots of 1/8 the width (so a short strip stays left-aligned instead of stretching). */
@Composable
internal fun HourlyBlock(items: List<HourCell>, modifier: Modifier = Modifier) {
    BoxWithConstraints(modifier.fillMaxWidth().height(HOURLY_DP.dp)) {
        val cell = maxWidth / maxOf(items.size, HOURLY_SLOTS)
        Row(Modifier.fillMaxHeight(), horizontalArrangement = Arrangement.Start) {
            for (c in items) HourCellView(c, Modifier.width(cell))
        }
    }
}

@Composable
private fun HourCellView(c: HourCell, modifier: Modifier) {
    Column(modifier.fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(c.label, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1)
        Spacer(Modifier.height(4.dp))
        if (c.glyph != null) Glyph(c.glyph, kind = "weather", tint = Haku.ink, size = HourGlyph) else Spacer(Modifier.height(HourGlyph))
        Spacer(Modifier.height(4.dp))
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            FitText(c.temp, HakuType.state, FitMin, Haku.ink)
        }
        Box(Modifier.height(20.dp), contentAlignment = Alignment.Center) {
            if (c.sub != null) Text(c.sub, style = HakuType.detail, color = Haku.inkMuted, maxLines = 1)
        }
    }
}
