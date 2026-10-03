package io.haku.tablet

import io.haku.tablet.ui.text.fitFontSize
import org.junit.Assert.assertEquals
import org.junit.Test

class FitTextTest {
    @Test
    fun fits_at_max_returns_max() {
        assertEquals(44f, fitFontSize(maxSp = 44f, minSp = 30f) { true })
    }

    @Test
    fun fits_only_at_or_below_36_returns_36_with_step_2() {
        // 44, 42, 40, 38 do not fit; 36 is the first (largest) size that does.
        assertEquals(36f, fitFontSize(maxSp = 44f, minSp = 30f, stepSp = 2f) { it <= 36f })
    }

    @Test
    fun never_fits_returns_min() {
        assertEquals(30f, fitFontSize(maxSp = 44f, minSp = 30f) { false })
    }

    @Test
    fun stops_at_the_first_size_that_fits() {
        val probed = mutableListOf<Float>()
        fitFontSize(maxSp = 44f, minSp = 30f) { probed += it; it <= 40f }
        assertEquals(listOf(44f, 42f, 40f), probed)
    }

    @Test
    fun min_is_the_floor_even_when_the_step_does_not_land_on_it() {
        // 44, 41, 38, 35, 32 then 29 is below the floor: the answer is min, not 29.
        assertEquals(31f, fitFontSize(maxSp = 44f, minSp = 31f, stepSp = 3f) { false })
        // A size that fits exactly at min is still min.
        assertEquals(30f, fitFontSize(maxSp = 44f, minSp = 30f) { it <= 30f })
    }

    @Test
    fun max_at_or_below_min_returns_min() {
        assertEquals(30f, fitFontSize(maxSp = 30f, minSp = 30f) { true })
        assertEquals(30f, fitFontSize(maxSp = 24f, minSp = 30f) { true })
    }
}
