package io.haku.tablet

import io.haku.tablet.data.Detail
import io.haku.tablet.data.DetailBlock
import io.haku.tablet.data.HourCell
import io.haku.tablet.data.MAX_CHART_POINTS
import io.haku.tablet.data.MAX_HOURLY
import io.haku.tablet.data.Run
import io.haku.tablet.data.parseDetail
import io.haku.tablet.data.parseRuns
import io.haku.tablet.ui.glyph.GLYPH_PATHS
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File

class DetailParseTest {
    private val demoDir = File("src/debug/assets/demo")
    private fun demo(id: String): Detail = parseDetail(File(demoDir, "detail_$id.json").readText())

    /** A detail with the given blocks (raw JSON) and nothing else. */
    private fun detail(vararg blocks: String): Detail =
        parseDetail("""{"v":1,"id":"x","title":"X","ts":1,"blocks":[${blocks.joinToString(",")}]}""")

    private fun chart(
        series: String = """[{"label":"S","tone":"water","runs":[{"i":0,"v":[1,2,3]}]}]""",
        count: Int = 10,
        extra: String = "",
    ) = """{"type":"chart","start":0,"step":3600,"count":$count,"series":$series$extra}"""

    private fun DetailBlock.asChart() = this as DetailBlock.Chart
    private fun Run.values() = v.toList()

    // ---- the demo fixtures ----

    @Test
    fun every_demo_fixture_parses_with_its_blocks() {
        val expected = mapOf(
            "water" to listOf("Stats", "Chart", "Days"),
            "energy" to listOf("Stats", "Chart", "Days"),
            "gas" to listOf("Stats", "Chart", "Days"),
            "climate" to listOf("Stats", "Chart"),
            "weather" to listOf("Now", "Rows", "Forecast"),
            "laundry" to listOf("Rows", "Rows", "Rows"),
            "doors" to listOf("Rows", "Rows"),
        )
        for ((id, kinds) in expected) {
            val d = demo(id)
            assertEquals(id, d.id)
            assertEquals(1, d.v)
            assertEquals(1790905930L, d.ts)
            assertEquals("$id blocks", kinds, d.blocks.map { it::class.simpleName })
        }
    }

    @Test
    fun demo_charts_are_hourly_week_with_a_gap_or_a_fill() {
        for (id in listOf("water", "energy", "gas", "climate")) {
            val c = demo(id).blocks.filterIsInstance<DetailBlock.Chart>().single()
            assertEquals(168, c.count)
            assertEquals(3600L, c.step)
            assertEquals(7, c.xTicks.size)
            assertNotNull("$id y", c.y)
            assertFalse("$id has data", c.isEmpty)
            for (s in c.series) for (r in s.runs) assertTrue("$id run in range", r.i >= 0 && r.end <= c.count)
        }
        val water = demo("water").blocks.filterIsInstance<DetailBlock.Chart>().single()
        assertTrue("water has a gap", water.series.single().runs.size >= 2)
        assertTrue(water.series.single().fill)
        val climate = demo("climate").blocks.filterIsInstance<DetailBlock.Chart>().single()
        assertEquals(listOf("heat", "cool"), climate.series.map { it.tone })
        assertTrue("climate has a one-bucket run", climate.series.any { s -> s.runs.any { it.v.size == 1 } })
        assertEquals("Today", demo("water").blocks.filterIsInstance<DetailBlock.Days>().single().items.last().label)
    }

    @Test
    fun demo_weather_glyphs_are_shipped_glyphs() {
        val days = demo("weather").blocks.filterIsInstance<DetailBlock.Forecast>().single().days
        assertEquals(3, days.size)
        for (d in days) assertTrue("${d.glyph} is not a bundled glyph", d.glyph in GLYPH_PATHS)
        assertNull(days.last().sub)
    }

    @Test
    fun demo_gas_has_a_note_and_history_only_for_today() {
        val d = demo("gas")
        assertNotNull(d.note)
        val c = d.blocks.filterIsInstance<DetailBlock.Chart>().single()
        assertTrue(c.series.single().runs.single().i >= 148)
    }

    @Test
    fun demo_row_glyphs_are_shipped_glyphs() {
        for (id in listOf("laundry", "doors")) {
            for (b in demo(id).blocks.filterIsInstance<DetailBlock.Rows>()) {
                for (it in b.items) if (it.glyph != null) assertTrue("${it.glyph}", it.glyph in GLYPH_PATHS)
            }
        }
    }

    // ---- the top level ----

    @Test
    fun top_level_defaults_and_note() {
        val d = parseDetail("""{"blocks":[]}""")
        assertEquals(Detail(v = 1, id = "", title = "", ts = 0, note = null, blocks = emptyList()), d)
        assertEquals("History unavailable", parseDetail("""{"note":"History unavailable"}""").note)
        assertNull("a blank note is no note", parseDetail("""{"note":"  "}""").note)
        assertTrue("no blocks key", parseDetail("{}").blocks.isEmpty())
        assertTrue("blocks of the wrong type", parseDetail("""{"blocks":"nope"}""").blocks.isEmpty())
    }

    @Test
    fun a_top_level_that_is_not_an_object_throws() {
        for (body in listOf("[]", "5", "\"x\"", "null", "not json", "")) {
            try {
                parseDetail(body)
                fail("expected a throw for <$body>")
            } catch (_: Exception) {
            }
        }
    }

    @Test
    fun unknown_and_malformed_blocks_are_skipped_and_the_rest_kept() {
        val d = detail(
            """{"type":"sparkline","points":[1,2]}""",
            """{"items":[{"label":"a","value":"b"}]}""",               // no type
            """{"type":"stats","items":"nope"}""",                      // items of the wrong type
            """{"type":"chart"}""",                                     // nothing to plot, nothing to say
            """{"type":"days"}""",
            """{"type":"forecast","days":{}}""",
            """{"type":"rows","items":[]}""",
            "42", "\"str\"", "null", "[]",
            """{"type":"stats","items":[{"label":"Now","value":"1"}]}""",
        )
        assertEquals(listOf(DetailBlock.Stats(listOf(io.haku.tablet.data.StatItem("Now", "1")))), d.blocks)
    }

    @Test
    fun a_block_with_the_wrong_typed_type_key_is_skipped() {
        assertTrue(detail("""{"type":{"a":1},"items":[]}""", """{"type":null}""").blocks.isEmpty())
    }

    @Test
    fun items_missing_a_required_field_are_dropped_not_the_block() {
        val s = detail("""{"type":"stats","items":[{"label":"A"},{"value":"v"},"x",{"label":"B","value":"2"}]}""")
            .blocks.single() as DetailBlock.Stats
        assertEquals(listOf("B"), s.items.map { it.label })
        val r = detail("""{"type":"rows","items":[{"label":"A"},{"label":"B","value":"2"}]}""").blocks.single() as DetailBlock.Rows
        assertEquals(listOf("B"), r.items.map { it.label })
        val f = detail("""{"type":"forecast","days":[{"glyph":"weather-rainy"},{"label":"Fri"}]}""").blocks.single() as DetailBlock.Forecast
        assertEquals(listOf("Fri"), f.days.map { it.label })
    }

    // ---- optional fields ----

    @Test
    fun missing_optional_fields_are_null_or_empty() {
        val d = detail(
            """{"type":"stats","items":[{"label":"Now","value":"4 L"},{"label":"Today","value":"1","sub":"$1"}]}""",
            """{"type":"forecast","days":[{"label":"Fri","glyph":"weather-rainy","cond":"Rain"},{"label":"Sat"}]}""",
            """{"type":"rows","items":[{"label":"A","value":"b"},{"glyph":"door-open","tone":"amber","label":"C","value":"d","sub":"e"}]}""",
            chart(),
        )
        val stats = d.blocks[0] as DetailBlock.Stats
        assertNull(stats.items[0].sub)
        assertEquals("$1", stats.items[1].sub)
        val days = (d.blocks[1] as DetailBlock.Forecast).days
        assertEquals(null, days[0].hi); assertEquals(null, days[0].lo); assertEquals(null, days[0].sub)
        assertEquals("", days[1].glyph); assertEquals("", days[1].cond)
        val rows = d.blocks[2] as DetailBlock.Rows
        assertNull(rows.title)
        assertEquals(listOf(null, "door-open"), rows.items.map { it.glyph })
        assertEquals(listOf(null, "amber"), rows.items.map { it.tone })
        assertEquals(listOf(null, "e"), rows.items.map { it.sub })
        val c = d.blocks[3].asChart()
        assertNull(c.title); assertNull(c.empty); assertNull(c.y)
        assertTrue(c.xTicks.isEmpty())
        assertFalse(c.series.single().fill)
    }

    @Test
    fun hi_lo_and_sub_that_are_blank_count_as_absent() {
        val f = detail("""{"type":"forecast","days":[{"label":"Fri","hi":"","lo":" ","sub":""}]}""").blocks.single() as DetailBlock.Forecast
        assertNull(f.days[0].hi); assertNull(f.days[0].lo); assertNull(f.days[0].sub)
    }

    @Test
    fun numbers_and_booleans_read_as_their_text() {
        val s = detail("""{"type":"stats","items":[{"label":"n","value":5}]}""").blocks.single() as DetailBlock.Stats
        assertEquals("5", s.items.single().value)
    }

    // ---- clamps ----

    @Test
    fun counts_are_clamped() {
        fun items(n: Int) = (1..n).joinToString(",") { """{"label":"l$it","value":"v$it"}""" }
        val d = detail(
            """{"type":"stats","items":[${items(9)}]}""",
            """{"type":"days","items":[${items(12)}]}""",
            """{"type":"forecast","days":[${(1..8).joinToString(",") { """{"label":"d$it"}""" }}]}""",
            """{"type":"rows","items":[${items(45)}]}""",
        )
        assertEquals(6, (d.blocks[0] as DetailBlock.Stats).items.size)
        assertEquals(8, (d.blocks[1] as DetailBlock.Days).items.size)
        assertEquals(5, (d.blocks[2] as DetailBlock.Forecast).days.size)
        assertEquals(30, (d.blocks[3] as DetailBlock.Rows).items.size)
        // The first ones are the ones kept.
        assertEquals("l1", (d.blocks[0] as DetailBlock.Stats).items.first().label)
    }

    @Test
    fun series_are_clamped_to_four() {
        val s = (1..6).joinToString(",", "[", "]") { """{"label":"s$it","runs":[{"i":0,"v":[1]}]}""" }
        val c = detail(chart(series = s)).blocks.single().asChart()
        assertEquals(listOf("s1", "s2", "s3", "s4"), c.series.map { it.label })
    }

    @Test
    fun chart_points_are_clamped_to_2000_in_total() {
        val big = (0 until 1500).joinToString(",", "[", "]") { "1" }
        val s = (1..3).joinToString(",", "[", "]") { """{"label":"s$it","runs":[{"i":0,"v":$big}]}""" }
        val c = detail(chart(series = s, count = 1500)).blocks.single().asChart()
        assertEquals(MAX_CHART_POINTS, c.series.sumOf { s2 -> s2.runs.sumOf { it.v.size } })
        assertEquals(1500, c.series[0].runs.single().v.size)
        assertEquals(500, c.series[1].runs.single().v.size)
        assertTrue("the third has nothing left", c.series[2].runs.isEmpty())
    }

    @Test
    fun ticks_are_capped() {
        val ticks = (0 until 100).joinToString(",") { """{"i":$it,"label":"t"}""" }
        val c = detail(chart(count = 100, extra = ""","x":{"ticks":[$ticks]}""")).blocks.single().asChart()
        assertEquals(24, c.xTicks.size)
    }

    // ---- runs: gaps, clipping ----

    private fun runs(json: String, count: Int = 20, budget: Int = 2000) =
        parseRuns(Json.parseToJsonElement(json) as JsonArray, count, budget)

    @Test
    fun a_non_number_splits_the_run() {
        val r = runs("""[{"i":10,"v":[1,"x",null,2,3,true,4,[5],{"a":1}]}]""")
        assertEquals(listOf(10, 13, 16), r.map { it.i })
        assertEquals(listOf(listOf(1f), listOf(2f, 3f), listOf(4f)), r.map { it.values() })
    }

    @Test
    fun leading_trailing_and_only_gaps() {
        assertEquals(listOf(11), runs("""[{"i":10,"v":[null,5,null]}]""").map { it.i })
        assertTrue(runs("""[{"i":0,"v":[null,"a"]}]""").isEmpty())
        assertTrue(runs("""[{"i":0,"v":[]}]""").isEmpty())
    }

    @Test
    fun a_string_that_looks_like_a_number_is_a_gap() {
        assertEquals(listOf(listOf(1f), listOf(3f)), runs("""[{"i":0,"v":[1,"2",3]}]""").map { it.values() })
    }

    @Test
    fun runs_outside_the_buckets_are_clipped() {
        val r = runs("""[{"i":-2,"v":[1,2,3]},{"i":18,"v":[7,8,9,10]},{"i":20,"v":[1]},{"i":99,"v":[1]}]""", count = 20)
        assertEquals(listOf(0 to listOf(3f), 18 to listOf(7f, 8f)), r.map { it.i to it.values() })
    }

    @Test
    fun a_huge_start_index_cannot_wrap_around() {
        assertTrue(runs("""[{"i":2147483647,"v":[1,2,3]}]""", count = 20).isEmpty())
        assertTrue(runs("""[{"i":-2147483648,"v":[1,2,3]}]""", count = 20).isEmpty())
    }

    @Test
    fun malformed_runs_are_skipped_and_good_ones_kept() {
        val r = runs("""[{"i":"a","v":[1]},{"i":1},{"v":[1]},"x",{"i":2,"v":"nope"},{"i":3,"v":[9]}]""")
        assertEquals(listOf(3 to listOf(9f)), r.map { it.i to it.values() })
    }

    @Test
    fun budget_cuts_a_run_short() {
        val r = runs("""[{"i":0,"v":[1,2,3,4,5]},{"i":10,"v":[1,2]}]""", budget = 3)
        assertEquals(listOf(0 to listOf(1f, 2f, 3f)), r.map { it.i to it.values() })
    }

    @Test
    fun fractions_and_negatives_survive() {
        val r = runs("""[{"i":0,"v":[1.5,-2.25,0,1e2]}]""")
        assertEquals(listOf(1.5f, -2.25f, 0f, 100f), r.single().values())
    }

    @Test
    fun runs_compare_by_content() {
        assertEquals(Run(2, floatArrayOf(1f, 2f)), Run(2, floatArrayOf(1f, 2f)))
        assertEquals(Run(2, floatArrayOf(1f)).hashCode(), Run(2, floatArrayOf(1f)).hashCode())
        assertFalse(Run(2, floatArrayOf(1f)) == Run(2, floatArrayOf(2f)))
        assertFalse(Run(2, floatArrayOf(1f)) == Run(3, floatArrayOf(1f)))
        assertEquals(demo("water"), demo("water"))
    }

    // ---- the y axis ----

    @Test
    fun y_missing_or_unusable_is_null() {
        fun y(json: String) = detail(chart(extra = ""","y":$json""")).blocks.single().asChart().y
        assertNull(y("""{"min":5,"max":5}"""))
        assertNull(y("""{"min":10,"max":0,"ticks":[{"v":5,"label":"5"}]}"""))
        assertNull(y("""{"min":0}"""))
        assertNull(y("""{"min":"0","max":"9"}"""))
        assertNull(y("""[]"""))
        assertNull(y("""null"""))
    }

    @Test
    fun y_keeps_its_scale_and_good_ticks() {
        val c = detail(
            chart(extra = ""","y":{"min":0,"max":60.5,"ticks":[{"v":0,"label":"0"},{"label":"no v"},{"v":30,"label":"30 L"},"x"]}"""),
        ).blocks.single().asChart()
        val y = c.y!!
        assertEquals(0f, y.min, 0f)
        assertEquals(60.5f, y.max, 0f)
        assertEquals(listOf("0", "30 L"), y.ticks.map { it.label })
        assertEquals(listOf(0f, 30f), y.ticks.map { it.v })
    }

    @Test
    fun a_y_without_ticks_is_still_a_scale() {
        val y = detail(chart(extra = ""","y":{"min":-5,"max":5}""")).blocks.single().asChart().y!!
        assertTrue(y.ticks.isEmpty())
    }

    // ---- chart extras ----

    @Test
    fun chart_with_no_runs_is_empty_and_keeps_its_text() {
        val c = detail("""{"type":"chart","count":168,"series":[{"label":"W","runs":[]}],"empty":"No history yet"}""")
            .blocks.single().asChart()
        assertTrue(c.isEmpty)
        assertEquals("No history yet", c.empty)
        val noSeries = detail("""{"type":"chart","empty":"No history yet"}""").blocks.single().asChart()
        assertTrue(noSeries.isEmpty)
        assertTrue(noSeries.series.isEmpty())
    }

    @Test
    fun x_ticks_and_series_fields() {
        val c = detail(
            chart(
                series = """[{"label":"Water","tone":"water","fill":true,"runs":[{"i":0,"v":[1]}]},{"label":"B","fill":"yes","runs":[]}]""",
                extra = ""","title":"Per hour","x":{"ticks":[{"i":7,"label":"Thu"},{"label":"bad"},{"i":"x","label":"bad"},{"i":30}]}""",
            ),
        ).blocks.single().asChart()
        assertEquals("Per hour", c.title)
        assertEquals(listOf(7 to "Thu", 30 to ""), c.xTicks.map { it.i to it.label })
        assertEquals(listOf("water", null), c.series.map { it.tone })
        assertEquals(listOf(true, false), c.series.map { it.fill })
        assertEquals(3600L, c.step)
    }

    @Test
    fun a_negative_or_missing_count_clips_every_run() {
        assertTrue(detail(chart(count = -5)).blocks.single().asChart().isEmpty)
        val noCount = detail("""{"type":"chart","series":[{"runs":[{"i":0,"v":[1,2]}]}]}""").blocks.single().asChart()
        assertEquals(0, noCount.count)
        assertTrue(noCount.isEmpty)
    }

    // ---- the weather panel: columns, now, hourly, compact outlook, strong tick ----

    private fun kinds(blocks: List<DetailBlock>) = blocks.map { it::class.simpleName }

    private fun stat(label: String, col: String? = null) =
        """{"type":"stats"${if (col == null) "" else ",\"col\":$col"},"items":[{"label":"$label","value":"v"}]}"""

    private fun labels(blocks: List<DetailBlock>) = blocks.map { (it as DetailBlock.Stats).items.single().label }

    @Test
    fun col_splits_the_blocks_into_two_columns_in_order() {
        val d = detail(
            stat("a"), stat("b", "1"), stat("c", "0"),
            stat("d", "7"),            // above range: the right column
            stat("e", "-3"),           // below range: the left
            stat("f", "\"1\""),        // a string is not a number: the left
            stat("g", "1.5"),          // nor is a fraction
        )
        assertEquals(listOf("a", "c", "e", "f", "g"), labels(d.blocks))
        assertEquals(listOf("b", "d"), labels(d.right))
    }

    @Test
    fun a_payload_without_col_has_nothing_on_the_right() {
        val d = detail(stat("a"), stat("b"))
        assertEquals(2, d.blocks.size)
        assertTrue(d.right.isEmpty())
    }

    @Test
    fun a_now_block_needs_a_temp_and_drops_blank_extras() {
        val now = detail(
            """{"type":"now","glyph":"weather-rainy","temp":"7°","cond":"Rainy","hilo":"H 12°  L 3°","sub":"Updated 6:20 PM"}""",
        ).blocks.single()
        assertEquals(DetailBlock.Now("weather-rainy", "7°", "Rainy", "H 12°  L 3°", "Updated 6:20 PM"), now)
        val bare = detail("""{"type":"now","temp":"--°","cond":"","hilo":" "}""").blocks.single()
        assertEquals(DetailBlock.Now(null, "--°", null, null, null), bare)
        assertTrue(detail("""{"type":"now","cond":"Rainy"}""", """{"type":"now","temp":""}""").blocks.isEmpty())
    }

    @Test
    fun an_hourly_block_keeps_cells_with_a_label_and_a_temp() {
        val h = detail(
            """{"type":"hourly","items":[
                {"label":"7 PM","glyph":"weather-rainy","temp":"7°","sub":"10%"},
                {"label":"8 PM"},{"temp":"1°"},"x",
                {"label":"9 PM","temp":"6°","glyph":"","sub":" "}]}""",
        ).blocks.single() as DetailBlock.Hourly
        assertEquals(listOf(HourCell("7 PM", "weather-rainy", "7°", "10%"), HourCell("9 PM", null, "6°", null)), h.items)
        assertTrue(detail("""{"type":"hourly","items":[]}""", """{"type":"hourly"}""").blocks.isEmpty())
    }

    @Test
    fun an_hourly_block_clamps_to_twelve_cells() {
        val cells = (1..15).joinToString(",") { """{"label":"$it PM","temp":"$it°"}""" }
        val h = detail("""{"type":"hourly","items":[$cells]}""").blocks.single() as DetailBlock.Hourly
        assertEquals(12, MAX_HOURLY)
        assertEquals(MAX_HOURLY, h.items.size)
        assertEquals("12 PM", h.items.last().label)
    }

    @Test
    fun forecast_style_compact_is_a_flag_and_anything_else_is_the_columns() {
        val day = """{"label":"Fri","glyph":"weather-rainy","cond":"Rainy","hi":"12°"}"""
        fun forecast(style: String) =
            detail("""{"type":"forecast"$style,"days":[$day]}""").blocks.single() as DetailBlock.Forecast
        assertTrue(forecast(",\"style\":\"compact\"").compact)
        assertFalse(forecast("").compact)
        assertFalse(forecast(",\"style\":\"wide\"").compact)
        assertFalse(forecast(",\"style\":7").compact)
    }

    @Test
    fun a_strong_x_tick_needs_a_real_true() {
        val c = detail(
            chart(extra = ""","x":{"ticks":[{"i":4,"label":"Now","strong":true},{"i":5,"label":"a","strong":"true"},{"i":6,"label":"b"}]}"""),
        ).blocks.single().asChart()
        assertEquals(listOf(true, false, false), c.xTicks.map { it.strong })
    }

    @Test
    fun the_v1_weather_payload_still_parses_as_one_column() {
        val d = parseDetail(File("src/test/resources/detail_weather_v1.json").readText())
        assertEquals(listOf("Stats", "Forecast"), kinds(d.blocks))
        assertTrue(d.right.isEmpty())
        assertFalse((d.blocks[1] as DetailBlock.Forecast).compact)
    }

    @Test
    fun the_weather_demo_is_the_two_column_panel() {
        val d = demo("weather")
        assertEquals(listOf("Now", "Rows", "Forecast"), kinds(d.blocks))
        assertEquals(listOf("Hourly", "Chart"), kinds(d.right))
        assertNotNull("the weather entity's attribution", d.note)
        val now = d.blocks[0] as DetailBlock.Now
        assertTrue(now.glyph in GLYPH_PATHS)
        assertNotNull(now.hilo)
        assertEquals("the cold-day worst case: every fact row", 6, (d.blocks[1] as DetailBlock.Rows).items.size)
        assertTrue((d.blocks[2] as DetailBlock.Forecast).compact)
        val hourly = d.right[0] as DetailBlock.Hourly
        assertEquals(8, hourly.items.size)
        for (c in hourly.items) assertTrue("${c.glyph} is not a bundled glyph", c.glyph in GLYPH_PATHS)
        val chart = d.right[1] as DetailBlock.Chart
        assertEquals(49, chart.count)
        assertEquals(listOf("Observed", "Forecast"), chart.series.map { it.label })
        assertEquals("only Now is strong", listOf(24), chart.xTicks.filter { it.strong }.map { it.i })
        for (s in chart.series) assertTrue("${s.label} has a point on Now", s.runs.any { 24 in it.i until it.end })
        assertNotNull(chart.y)
    }

    @Test
    fun the_tonight_demo_has_only_a_low() {
        val now = demo("weather_tonight").blocks[0] as DetailBlock.Now
        assertNotNull(now.hilo)
        assertTrue(now.hilo, now.hilo!!.startsWith("L ") && !now.hilo!!.contains("H"))
    }

    @Test
    fun the_forecast_down_demo_is_the_hero_and_facts_beside_an_observed_only_chart() {
        val d = demo("weather_nofc")
        assertEquals(listOf("Now", "Rows"), kinds(d.blocks))
        assertEquals(listOf("Chart"), kinds(d.right))
        assertEquals(listOf("Observed"), (d.right.single() as DetailBlock.Chart).series.map { it.label })
        assertNull((d.blocks[0] as DetailBlock.Now).hilo)
    }
}
