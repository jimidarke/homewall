package io.haku.tablet.ui.text

import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.LocalTextStyle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorProducer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp

/**
 * The largest size from [maxSp] down to [minSp] in [stepSp] steps for which [fits] is true; [minSp] if none
 * is (so the caller ellipsizes at the floor). [minSp] is always the last candidate even when the steps do
 * not land on it. Pure, so the shrink policy is testable without a text engine.
 */
fun fitFontSize(maxSp: Float, minSp: Float, stepSp: Float = 2f, fits: (Float) -> Boolean): Float {
    require(stepSp > 0f) { "stepSp must be positive" }
    var i = 0
    var size = maxSp
    while (size > minSp) {   // false for NaN too, so bad input falls to the floor instead of looping
        if (fits(size)) return size
        size = maxSp - ++i * stepSp
    }
    return minSp
}

/**
 * One line of [text] that shrinks from [style]'s size toward [minSize] to fit the width it is given, and
 * ellipsizes only if it still does not fit at [minSize]. Measures once per (text, style, width), not per frame.
 */
@Composable
fun FitText(text: String, style: TextStyle, minSize: TextUnit, color: Color, modifier: Modifier = Modifier) {
    val producer = remember(color) { ColorProducer { color } }
    FitText(text, style, minSize, producer, modifier)
}

/** [FitText] whose [color] is read while drawing, so an animated colour redraws the text without recomposing it. */
@Composable
fun FitText(text: String, style: TextStyle, minSize: TextUnit, color: ColorProducer, modifier: Modifier = Modifier) {
    // Resolve against the ambient style as Text() would, and measure and draw with that same style.
    val resolved = LocalTextStyle.current.merge(style)
    val measurer = rememberTextMeasurer()
    BoxWithConstraints(modifier) {
        val widthPx = constraints.maxWidth
        val shrinkable = constraints.hasBoundedWidth && resolved.fontSize.isSp && minSize.isSp
        val size = if (!shrinkable) resolved.fontSize else remember(text, resolved, minSize, widthPx, measurer) {
            fitFontSize(resolved.fontSize.value, minSize.value) { sp ->
                !measurer.measure(
                    text = text,
                    style = resolved.copy(fontSize = sp.sp),
                    overflow = TextOverflow.Clip,
                    softWrap = false,
                    maxLines = 1,
                    constraints = Constraints(maxWidth = widthPx),
                ).didOverflowWidth
            }.sp
        }
        BasicText(
            text = text,
            style = resolved.copy(fontSize = size),
            overflow = TextOverflow.Ellipsis,
            softWrap = false,
            maxLines = 1,
            color = color,
        )
    }
}
