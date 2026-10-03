package io.haku.tablet.ui

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType
import java.text.SimpleDateFormat
import java.time.ZoneId
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * "9:17 PM", whatever the device locale: the wall runs en-CA, whose "p.m." would sit oddly beside the
 * sidecar's own "3:30 PM" times. The date stays in the device locale. [zone] is the house's own unless a
 * test pins it.
 */
internal fun formatTime(ms: Long, zone: ZoneId = ZoneId.systemDefault()): String =
    SimpleDateFormat("h:mm a", Locale.US).apply { timeZone = TimeZone.getTimeZone(zone) }.format(Date(ms))

internal fun formatDate(ms: Long): String = SimpleDateFormat("EEEE, MMMM d", Locale.getDefault()).format(Date(ms))

/** Time and date. Recomposes only at minute boundaries (and when the screen restarts), never per second. */
@Composable
fun Clock(modifier: Modifier = Modifier) {
    val now by remember { minuteTicks() }.collectAsStateWithLifecycle(initialValue = System.currentTimeMillis())
    val minute = now / 60_000L   // the text is the same for every ms within a minute
    val time = remember(minute) { formatTime(minute * 60_000L) }
    val date = remember(minute) { formatDate(minute * 60_000L) }
    Row(modifier) {
        Text(time, style = HakuType.clock, color = Haku.ink, modifier = Modifier.alignByBaseline())
        Spacer(Modifier.width(16.dp))
        Text(date, style = HakuType.date, color = Haku.inkMuted, modifier = Modifier.alignByBaseline())
    }
}
