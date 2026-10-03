package io.haku.tablet

import io.haku.tablet.data.Door
import io.haku.tablet.ui.cards.doorsShown
import org.junit.Assert.assertEquals
import org.junit.Test

class DoorsOrderTest {
    private fun door(id: String, state: String) = Door(id, id, state, "5m", "normal", "door")
    private fun shown(doors: List<Door>, fit: Int) = doorsShown(doors, fit).map { it.id }

    @Test
    fun open_and_unknown_doors_come_before_closed() {
        val doors = listOf(door("front", "closed"), door("side", "closed"), door("garage", "unknown"), door("back", "open"))
        // A 1x1 tile fits 2 rows: an open door must never be the one cut off.
        assertEquals(listOf("garage", "back"), shown(doors, fit = 2))
        // Stable: closed doors keep the sidecar's order after the others, and the card still caps at 3.
        assertEquals(listOf("garage", "back", "front"), shown(doors, fit = 5))
    }

    @Test
    fun all_closed_keeps_sidecar_order() {
        val doors = listOf(door("front", "closed"), door("back", "closed"), door("side", "closed"))
        assertEquals(listOf("front", "back"), shown(doors, fit = 2))
        assertEquals(listOf("front", "back", "side"), shown(doors, fit = 3))
    }
}
