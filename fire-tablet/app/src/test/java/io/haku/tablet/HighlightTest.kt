package io.haku.tablet

import io.haku.tablet.ui.cards.isHighlighted
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HighlightTest {
    @Test
    fun null_after_gap_never_highlights() {
        // highlightAfter is null at cold start and after a failed poll: nothing is new, however recent.
        assertFalse(isHighlighted(1_790_000_000L, null))
        assertFalse(isHighlighted(null, null))
    }

    @Test
    fun newer_item_highlighted() {
        assertTrue(isHighlighted(1_790_000_001L, 1_790_000_000L))
        assertTrue(isHighlighted(1_790_000_600L, 1_790_000_000L))
    }

    @Test
    fun equal_not_highlighted() {
        assertFalse(isHighlighted(1_790_000_000L, 1_790_000_000L))
        assertFalse(isHighlighted(1_789_999_999L, 1_790_000_000L))
        assertFalse("an item with no time is never new", isHighlighted(null, 1_790_000_000L))
    }
}
