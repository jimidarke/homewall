package io.haku.tablet.ui.glyph

import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import java.util.concurrent.ConcurrentHashMap

/** The MDI subset the tablet ships (Contract 2). Path data lives in the generated `GlyphData.kt`. */
object Glyphs {
    private val cache = ConcurrentHashMap<String, ImageVector>()

    /** Kind -> glyph used when the sidecar sends none, or one this build does not ship (Contract 2.3). */
    private val kindDefaults = mapOf(
        "doors" to "door",
        "laundry" to "washing-machine",
        "water" to "water-outline",
        "energy" to "flash",
        "gas" to "meter-gas",
        "climate" to "thermostat",
        "weather" to "weather-partly-cloudy",
        "calendar" to "calendar",
        "timeline" to "history",
    )

    /** The glyph's vector, parsed on first use and cached; null if this build does not ship [name]. */
    fun vector(name: String): ImageVector? {
        val d = GLYPH_PATHS[name] ?: return null
        return cache.getOrPut(name) { build(name, d) }
    }

    /** Default glyph name for a module kind, or "" if it has none. */
    fun defaultFor(kind: String): String = kindDefaults[kind].orEmpty()

    /**
     * The name [resolve] draws: [glyph] if shipped, else the kind's default, else "". Cards take their accent
     * from this name, so the accent always matches the glyph on screen.
     */
    fun nameFor(glyph: String, kind: String): String = if (glyph in GLYPH_PATHS) glyph else defaultFor(kind)

    /** [glyph] if shipped, else the kind's default, else null (the card then shows no glyph). */
    fun resolve(glyph: String, kind: String): ImageVector? = vector(nameFor(glyph, kind))

    private fun build(name: String, d: String): ImageVector =
        ImageVector.Builder(
            name = name, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f,
        ).addPath(
            pathData = PathParser().parsePathString(d).toNodes(),
            fill = SolidColor(Color.Black),
        ).build()
}

/** Draws [name], or the [kind]'s default if [name] is unknown; draws nothing if neither resolves. */
@Composable
fun Glyph(name: String, kind: String, tint: Color, size: Dp, modifier: Modifier = Modifier) {
    val vector = Glyphs.resolve(name, kind) ?: return
    Icon(imageVector = vector, contentDescription = null, tint = tint, modifier = modifier.size(size))
}
