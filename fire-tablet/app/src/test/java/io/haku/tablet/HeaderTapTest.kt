package io.haku.tablet

import io.haku.tablet.ui.HeaderTap
import io.haku.tablet.ui.headerTapAction
import org.junit.Assert.assertEquals
import org.junit.Test

class HeaderTapTest {
    private val both = listOf(false, true)

    @Test
    fun an_open_detail_closes_first() {
        for (peeking in both) for (hasPhoto in both) {
            val action = headerTapAction(detailOpen = true, peeking, hasPhoto)
            assertEquals("peeking=$peeking photo=$hasPhoto", HeaderTap.CLOSE_DETAIL, action)
        }
    }

    @Test
    fun a_tap_while_peeking_ends_the_peek() {
        // Even if the photo went away mid-peek: the tap must still bring the UI back.
        for (hasPhoto in both) assertEquals(HeaderTap.END_PEEK, headerTapAction(false, peeking = true, hasPhoto))
    }

    @Test
    fun a_tap_starts_a_peek_only_with_a_photo() {
        assertEquals(HeaderTap.START_PEEK, headerTapAction(false, peeking = false, hasPhoto = true))
        // Night, an empty NAS or no config yet: nothing to show, so the tap does nothing.
        assertEquals(HeaderTap.NONE, headerTapAction(false, peeking = false, hasPhoto = false))
    }

    @Test
    fun back_closes_what_is_open_and_never_starts_a_peek() {
        // Back asks with hasPhoto = false.
        assertEquals(HeaderTap.CLOSE_DETAIL, headerTapAction(detailOpen = true, peeking = true, hasPhoto = false))
        assertEquals(HeaderTap.END_PEEK, headerTapAction(detailOpen = false, peeking = true, hasPhoto = false))
        assertEquals(HeaderTap.NONE, headerTapAction(detailOpen = false, peeking = false, hasPhoto = false))
    }
}
