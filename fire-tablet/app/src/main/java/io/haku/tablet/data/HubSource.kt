package io.haku.tablet.data

/**
 * Where the dashboard gets its data: the real sidecar, or a debug demo that replays canned
 * states. Every call returns a [Fetch]; nothing throws.
 */
interface HubSource {
    suspend fun config(): Fetch<HubConfig>
    suspend fun state(): Fetch<HubState>

    /** Image names only; the tablet builds the image URLs itself via [background]. */
    suspend fun backgrounds(): Fetch<List<String>>

    /** One scaled JPEG. [blur] is a Gaussian radius, 0 means none. */
    suspend fun background(name: String, w: Int, h: Int, fit: String = "cover", blur: Int = 0): Fetch<ByteArray>

    /**
     * The detail panel's content for module [id] (`/api/detail/<id>`). A source with none answers 404, which
     * the panel treats like the sidecar's "no detail for this kind": it shows the tile instead.
     */
    suspend fun detail(id: String): Fetch<Detail> = Fetch.HttpError(404)
}
