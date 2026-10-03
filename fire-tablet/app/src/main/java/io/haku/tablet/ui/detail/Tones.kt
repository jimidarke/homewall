package io.haku.tablet.ui.detail

import androidx.compose.ui.graphics.Color
import io.haku.tablet.ui.theme.Haku

/** The sidecar's `tone` key as a design token (contract section 4). Null and any other key fall back to ink. */
fun toneColor(key: String?): Color = when (key) {
    "water" -> Haku.water
    "heat" -> Haku.heat
    "cool" -> Haku.cool
    "washer" -> Haku.washer
    "dryer" -> Haku.dryer
    "sage" -> Haku.sage
    "ink" -> Haku.ink
    "muted" -> Haku.inkMuted
    "amber" -> Haku.amber
    "coral" -> Haku.coral
    else -> Haku.ink
}
