package io.haku.tablet

import io.haku.tablet.ui.backdrop.ShuffleBag
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

class ShuffleBagTest {
    @Test
    fun `covers_all_each_round`() {
        val items = listOf("a", "b", "c", "d", "e")
        val bag = ShuffleBag<String>(Random(7)).apply { reset(items) }
        repeat(10) { round ->
            val drawn = List(items.size) { bag.next() }
            assertEquals("round $round", items.toSet(), drawn.toSet())
        }
    }

    @Test
    fun `no_immediate_repeat_across_rounds`() {
        val bag = ShuffleBag<String>(Random(42)).apply { reset(listOf("a", "b", "c")) }
        var last: String? = null
        repeat(200) { i ->
            val n = bag.next()
            assertNotEquals("draw $i repeats", last, n)
            last = n
        }
    }

    @Test
    fun `reset_same_set_keeps_queue`() {
        val bag = ShuffleBag<String>(Random(3)).apply { reset(listOf("a", "b", "c")) }
        val first = bag.next()
        bag.reset(listOf("c", "b", "a"))   // a list refresh in another order is the same set
        val rest = listOf(bag.next(), bag.next())
        assertEquals(setOf("a", "b", "c"), (rest + first).toSet())
    }

    @Test
    fun `removed_items_skipped`() {
        val bag = ShuffleBag<String>(Random(5)).apply { reset(listOf("a", "b", "c", "d")) }
        bag.next()
        bag.reset(listOf("a", "c"))
        repeat(20) {
            val n = bag.next()
            assertTrue("drew removed item $n", n == "a" || n == "c")
        }
    }

    @Test
    fun `empty_returns_null`() {
        val bag = ShuffleBag<String>(Random(1))
        assertTrue(bag.isEmpty)
        assertNull(bag.next())
        bag.reset(listOf("a"))
        assertFalse(bag.isEmpty)
        assertEquals("a", bag.next())
        assertEquals("a", bag.next())   // a single photo is allowed to repeat
        bag.reset(emptyList())
        assertTrue(bag.isEmpty)
        assertNull(bag.next())
    }
}
