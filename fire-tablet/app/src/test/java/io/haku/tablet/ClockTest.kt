package io.haku.tablet

import io.haku.tablet.ui.formatTime
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Locale

class ClockTest {
    private val saved = Locale.getDefault()

    @After
    fun restore() = Locale.setDefault(saved)

    @Test
    fun time_reads_am_pm_like_the_sidecar_whatever_the_device_locale() {
        // The wall's Fire OS runs en-CA, whose default "a" is "a.m."/"p.m.". The sidecar's times say "3:30 PM".
        for (locale in listOf(Locale.CANADA, Locale.US, Locale.FRANCE)) {
            Locale.setDefault(locale)
            val t = formatTime(1_790_822_530_000L)
            assertTrue("$locale gave '$t'", Regex("""\d{1,2}:\d{2} (AM|PM)""").matches(t))
        }
    }
}
