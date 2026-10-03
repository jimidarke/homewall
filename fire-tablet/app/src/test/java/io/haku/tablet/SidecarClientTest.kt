package io.haku.tablet

import io.haku.tablet.data.Fetch
import io.haku.tablet.data.SidecarClient
import io.haku.tablet.data.describe
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

class SidecarClientTest {
    private lateinit var server: MockWebServer
    private lateinit var client: SidecarClient
    private lateinit var base: String

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        base = server.url("/").toString().trimEnd('/')
        client = SidecarClient(base)
    }

    @After
    fun tearDown() = server.shutdown()

    @Test
    fun `config requests layout query`() = runTest {
        server.enqueue(MockResponse().setBody("""{"grid":{"cols":3,"rows":2},"modules":[]}"""))
        val r = SidecarClient(base, "tablet").config()
        assertTrue(r is Fetch.Ok)
        assertEquals(3, (r as Fetch.Ok).value.grid.cols)
        assertEquals("/api/config?layout=tablet", server.takeRequest().path)
    }

    @Test
    fun `state without layout has no query`() = runTest {
        server.enqueue(MockResponse().setBody("""{"ts":1790822530,"energy":{"tile":{"hero":"1.4 kW"}}}"""))
        val r = client.state()
        assertEquals("1.4 kW", (r as Fetch.Ok).value.tile("energy")!!.hero)
        assertEquals("/api/state", server.takeRequest().path)
    }

    @Test
    fun `500 is an http error`() = runTest {
        server.enqueue(MockResponse().setResponseCode(500))
        assertEquals(Fetch.HttpError(500), client.state())
    }

    @Test
    fun `malformed json is a parse error`() = runTest {
        server.enqueue(MockResponse().setBody("not json"))
        assertTrue(client.config() is Fetch.ParseError)
    }

    @Test
    fun `unreachable host is a network error`() = runTest {
        server.shutdown()
        assertTrue(client.state() is Fetch.NetworkError)
    }

    @Test
    fun `backgrounds parses names`() = runTest {
        server.enqueue(MockResponse().setBody("""{"images":[{"name":"a.jpg","url":"x"},{"url":"y"}]}"""))
        assertEquals(Fetch.Ok(listOf("a.jpg")), SidecarClient(base, "tablet").backgrounds())
        assertEquals("/api/backgrounds?layout=tablet", server.takeRequest().path)
    }

    @Test
    fun `backgrounds without images key is empty`() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        assertEquals(Fetch.Ok(emptyList<String>()), client.backgrounds())
    }

    @Test
    fun `background builds query and returns bytes`() = runTest {
        val bytes = byteArrayOf(1, 2, 3, 0x7f)
        server.enqueue(MockResponse().setBody(okio.Buffer().write(bytes)))
        val r = SidecarClient(base, "tablet").background("a b.jpg", 1024, 600, "cover", 8)
        assertTrue(r is Fetch.Ok)
        assertTrue(bytes.contentEquals((r as Fetch.Ok).value))
        val path = server.takeRequest().path!!
        assertTrue(path, path.startsWith("/api/background/a%20b.jpg?"))
        assertTrue(path, "layout=tablet" in path)
        assertTrue(path, "w=1024" in path)
        assertTrue(path, "h=600" in path)
        assertTrue(path, "fit=cover" in path)
        assertTrue(path, "blur=8" in path)
    }

    @Test
    fun `background omits blur zero`() = runTest {
        server.enqueue(MockResponse().setBody("x"))
        client.background("a.jpg", 256, 150)
        val path = server.takeRequest().path!!
        assertTrue(path, "blur=" !in path)
        assertTrue(path, "fit=cover" in path)
    }

    @Test
    fun `background 404 is an http error and unreachable is a network error`() = runTest {
        server.enqueue(MockResponse().setResponseCode(404))
        assertEquals(Fetch.HttpError(404), client.background("gone.jpg", 64, 64))
        server.shutdown()
        assertTrue(client.background("a.jpg", 64, 64) is Fetch.NetworkError)
        assertTrue(client.backgrounds() is Fetch.NetworkError)
    }

    @Test
    fun `detail requests the module's path with the layout and parses blocks`() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """{"v":1,"id":"water","title":"Water","ts":1790905930,"blocks":[
                    {"type":"stats","items":[{"label":"Now","value":"4.2 L/min"}]},
                    {"type":"mystery"}]}""",
            ),
        )
        val r = SidecarClient(base, "tablet").detail("water")
        assertTrue(r.describe(), r is Fetch.Ok)
        val d = (r as Fetch.Ok).value
        assertEquals("Water", d.title)
        assertEquals(1, d.blocks.size)
        assertEquals("/api/detail/water?layout=tablet", server.takeRequest().path)
    }

    @Test
    fun `detail without a layout has no query and encodes the id`() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        server.enqueue(MockResponse().setBody("{}"))
        assertTrue(client.detail("water") is Fetch.Ok)
        assertEquals("/api/detail/water", server.takeRequest().path)
        assertTrue(SidecarClient(base, "tablet").detail("a b/c") is Fetch.Ok)
        assertEquals("/api/detail/a%20b%2Fc?layout=tablet", server.takeRequest().path)
    }

    @Test
    fun `detail 404 is an http error and a non-object body is a parse error`() = runTest {
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":"no detail"}"""))
        assertEquals(Fetch.HttpError(404), client.detail("calendar"))
        server.enqueue(MockResponse().setBody("[]"))
        assertTrue(client.detail("water") is Fetch.ParseError)
        server.enqueue(MockResponse().setBody("not json"))
        assertTrue(client.detail("water") is Fetch.ParseError)
        server.shutdown()
        assertTrue(client.detail("water") is Fetch.NetworkError)
    }

    @Test
    fun `detail waits longer than a poll for a cold sidecar`() = runTest {
        // A client that gives up after 500 ms: polls fail on a slow body, while detail (15 s read) still succeeds.
        val impatient = SidecarClient(base, "tablet", OkHttpClient.Builder().readTimeout(500, TimeUnit.MILLISECONDS).build())
        server.enqueue(MockResponse().setBody("{}").setBodyDelay(1200, TimeUnit.MILLISECONDS))
        assertTrue(impatient.state() is Fetch.NetworkError)
        server.enqueue(MockResponse().setBody("""{"id":"slow"}""").setBodyDelay(1200, TimeUnit.MILLISECONDS))
        val r = impatient.detail("water")
        assertEquals(r.describe(), "slow", (r as Fetch.Ok).value.id)
    }

    @Test
    fun `describe names the failure for the banner and the logs`() {
        assertEquals("ok", Fetch.Ok(1).describe())
        assertEquals("http 502", Fetch.HttpError(502).describe())
        assertEquals("network: timeout", Fetch.NetworkError("timeout").describe())
        assertEquals("parse: bad json", Fetch.ParseError("bad json").describe())
    }
}
