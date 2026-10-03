package io.haku.tablet

import io.haku.tablet.data.DemoSource
import io.haku.tablet.data.Fetch
import io.haku.tablet.data.HubConfig
import io.haku.tablet.data.HubJson
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.HubState
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class DemoSourceTest {
    /** Stands in for the sidecar; DemoSource must delegate background calls here. */
    private class FakeReal : HubSource {
        val calls = mutableListOf<String>()
        override suspend fun config(): Fetch<HubConfig> = error("demo must not hit the real config")
        override suspend fun state(): Fetch<HubState> = error("demo must not hit the real state")
        override suspend fun backgrounds(): Fetch<List<String>> {
            calls += "backgrounds"
            return Fetch.Ok(listOf("a.jpg"))
        }
        override suspend fun background(name: String, w: Int, h: Int, fit: String, blur: Int): Fetch<ByteArray> {
            calls += "background $name $w $h $fit $blur"
            return Fetch.Ok(byteArrayOf(9))
        }
    }

    private val demoDir = File("src/debug/assets/demo")
    private fun read(path: String) = File(demoDir, path.removePrefix("demo/")).readText()

    @Test
    fun `cycle rotates every 10s`() = runTest {
        val paths = mutableListOf<String>()
        var now = 0L
        val src = DemoSource({ paths += it; """{"v":1}""" }, "cycle", FakeReal(), { now })
        for (t in listOf(0L, 10_000L, 20_000L, 30_000L)) {
            now = t
            src.state()
        }
        assertEquals(
            listOf("demo/quiet.json", "demo/busy.json", "demo/alert.json", "demo/quiet.json"),
            paths,
        )
    }

    @Test
    fun `fixed scenario reads its own file and config reads config json`() = runTest {
        val paths = mutableListOf<String>()
        val src = DemoSource({ paths += it; if (it.endsWith("config.json")) """{"modules":[]}""" else """{"v":1}""" },
            "alert", FakeReal(), { 20_000L })
        assertTrue(src.state() is Fetch.Ok)
        assertTrue(src.config() is Fetch.Ok)
        assertEquals(listOf("demo/alert.json", "demo/config.json"), paths)
    }

    @Test
    fun offline_scenario_fails_state_after_5s() = runTest {
        val paths = mutableListOf<String>()
        var now = 1_000L
        val src = DemoSource({ paths += it; if (it.endsWith("config.json")) """{"modules":[]}""" else """{"v":1}""" },
            "offline", FakeReal(), { now })
        now = 1_000L
        assertTrue("serves quiet at first", src.state() is Fetch.Ok)
        now = 5_999L
        assertTrue("still within 5 s", src.state() is Fetch.Ok)
        now = 6_000L
        assertEquals(Fetch.NetworkError("demo offline"), src.state())
        now = 600_000L
        assertEquals(Fetch.NetworkError("demo offline"), src.state())
        assertTrue("config keeps working", src.config() is Fetch.Ok)
        assertEquals(listOf("demo/quiet.json", "demo/quiet.json", "demo/config.json"), paths)
    }

    @Test
    fun degraded_scenario_serves_quiet_then_the_water_meter_out() = runTest {
        val paths = mutableListOf<String>()
        var now = 1_000L
        val src = DemoSource({ paths += it; read(it) }, "degraded", FakeReal(), { now })
        now = 5_999L
        assertTrue("quiet first, so the water card has a reading to hold", src.state() is Fetch.Ok)
        now = 6_000L
        val st = (src.state() as Fetch.Ok).value
        assertEquals(listOf("demo/quiet.json", "demo/degraded.json"), paths)
        assertTrue(st.stale("water"))
        assertEquals("-- L/min", st.tile("water")?.hero)
        assertFalse("only the water meter is out", st.stale("energy"))
    }

    @Test
    fun `a failed read or parse is a parse error`() = runTest {
        val missing = DemoSource({ throw java.io.FileNotFoundException(it) }, "busy", FakeReal())
        assertTrue(missing.state() is Fetch.ParseError)
        assertTrue(missing.config() is Fetch.ParseError)
        val garbage = DemoSource({ "not json" }, "busy", FakeReal())
        assertTrue(garbage.state() is Fetch.ParseError)
        assertTrue(garbage.config() is Fetch.ParseError)
    }

    @Test
    fun `backgrounds delegate to the real source`() = runTest {
        val real = FakeReal()
        val src = DemoSource(::read, "quiet", real)
        assertEquals(Fetch.Ok(listOf("a.jpg")), src.backgrounds())
        val r = src.background("a.jpg", 1024, 600, "cover", 8)
        assertTrue(r is Fetch.Ok)
        assertEquals(listOf("backgrounds", "background a.jpg 1024 600 cover 8"), real.calls)
    }

    @Test
    fun `detail reads demo detail_id json and parses it`() = runTest {
        val paths = mutableListOf<String>()
        val src = DemoSource({ paths += it; read(it) }, "quiet", FakeReal())
        val r = src.detail("water")
        assertTrue(r.toString(), r is Fetch.Ok)
        assertEquals("water", (r as Fetch.Ok).value.id)
        assertTrue(r.value.blocks.isNotEmpty())
        assertEquals(listOf("demo/detail_water.json"), paths)
    }

    @Test
    fun `a detail variant is read first and the plain detail is the fallback`() = runTest {
        val paths = mutableListOf<String>()
        val src = DemoSource(
            { paths += it; if (it == "demo/detail_weather_nofc.json") """{"v":1,"id":"nofc"}""" else read(it) },
            "quiet", FakeReal(), detailVariant = "nofc",
        )
        assertEquals("nofc", (src.detail("weather") as Fetch.Ok).value.id)
        assertEquals(listOf("demo/detail_weather_nofc.json"), paths)
        paths.clear()
        // water has no _nofc file: its plain detail is shown
        val water = DemoSource(
            { paths += it; if (it.contains("_nofc")) throw java.io.FileNotFoundException(it) else read(it) },
            "quiet", FakeReal(), detailVariant = "nofc",
        )
        assertEquals("water", (water.detail("water") as Fetch.Ok).value.id)
        assertEquals(listOf("demo/detail_water_nofc.json", "demo/detail_water.json"), paths)
    }

    @Test
    fun `a detail variant that is not a plain name is ignored`() = runTest {
        for (bad in listOf("../config", "a/b", "", "a b", "x.json")) {
            val paths = mutableListOf<String>()
            DemoSource({ paths += it; read(it) }, "quiet", FakeReal(), detailVariant = bad).detail("water")
            assertEquals(bad, listOf("demo/detail_water.json"), paths)
        }
    }

    @Test
    fun `detail with no demo asset is a 404, like a kind the sidecar has no detail for`() = runTest {
        val src = DemoSource(::read, "quiet", FakeReal())
        assertEquals(Fetch.HttpError(404), src.detail("calendar"))
        assertEquals(Fetch.HttpError(404), DemoSource({ throw java.io.FileNotFoundException(it) }, "quiet", FakeReal()).detail("water"))
    }

    @Test
    fun `detail ids that are not plain names are a 404 and never read`() = runTest {
        val paths = mutableListOf<String>()
        val src = DemoSource({ paths += it; """{"v":1}""" }, "quiet", FakeReal())
        for (id in listOf("../config", "a/b", "", "a b", "x.json")) assertEquals(id, Fetch.HttpError(404), src.detail(id))
        assertTrue(paths.isEmpty())
    }

    @Test
    fun `a detail asset that is not an object is a parse error`() = runTest {
        assertTrue(DemoSource({ "[]" }, "quiet", FakeReal()).detail("water") is Fetch.ParseError)
        assertTrue(DemoSource({ "not json" }, "quiet", FakeReal()).detail("water") is Fetch.ParseError)
    }

    @Test
    fun `a source with no detail of its own answers 404`() = runTest {
        assertEquals(Fetch.HttpError(404), FakeReal().detail("water"))
    }

    @Test
    fun `every demo fixture parses`() {
        val cfg = HubJson.parseConfig(File(demoDir, "config.json").readText())
        assertEquals(9, cfg.modules.size)
        for (name in listOf("quiet", "busy", "alert", "degraded")) {
            val st = HubJson.parseState(File(demoDir, "$name.json").readText())
            assertNotNull("$name ts", st.ts)
            for (m in cfg.modules.filter { it.tile.type != "agenda" }) {
                assertNotNull("$name.json missing tile for ${m.key}", st.tile(m.key))
            }
            for (m in cfg.modules.filter { it.tile.type == "agenda" }) {
                assertTrue("$name.json has no items for ${m.key}", st.items(m.key).isNotEmpty())
            }
        }
    }
}
