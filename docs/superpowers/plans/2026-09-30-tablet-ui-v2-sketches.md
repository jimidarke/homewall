# Tablet UI v2: reference code sketches

These sketches come from the design review. Tasks 17 and 18 adapt them. They are **sketches**: names follow the plan's Interfaces blocks, so fix up imports, types and edge cases as you build.

## Backdrop state (shared, read in the draw phase only)

```kotlin
class Photo(val sharp: ImageBitmap, val soft: ImageBitmap, val luma: Float)   // identity equality on purpose

@Stable
class BackdropState {
    var front: Photo? by mutableStateOf(null); private set   // fading in / current
    var back:  Photo? by mutableStateOf(null); private set   // fading out; null when idle
    val fade = Animatable(1f)                                 // 0 = all back, 1 = all front
    var rootSize by mutableStateOf(IntSize.Zero)

    /** Run from ONE LaunchedEffect(photo) in Backdrop; cancellation-safe. */
    suspend fun show(next: Photo?) {
        if (next === front) return
        back = front; front = next
        try {
            fade.snapTo(0f)
            fade.animateTo(1f, tween(1600, easing = LinearOutSlowInEasing))
        } finally { back = null }            // drop the old pair; GC frees it (no recycle())
    }
}
val LocalBackdrop = staticCompositionLocalOf<BackdropState?> { null }

// Opaque photos: draw back at alpha 1, then front at p over it. That gives a correct cross-fade.
// When fading to "no photo" (night / empty NAS), draw back at 1-p over the gradient instead.
internal fun backAlpha(front: Photo?, p: Float) = if (front == null) 1f - p else 1f
```

## Backdrop composable (one full-screen layer)

```kotlin
@Composable
fun Backdrop(photo: Photo?, state: BackdropState) {
    LaunchedEffect(photo) { state.show(photo) }
    Spacer(Modifier.fillMaxSize()
        .onSizeChanged { state.rootSize = it }
        .drawWithCache {
            val fallback = Brush.radialGradient(listOf(Haku.sage.copy(alpha = .35f), Haku.night),
                center = Offset(size.width * .2f, 0f), radius = size.maxDimension)
            val dst = IntSize(size.width.roundToInt(), size.height.roundToInt())
            onDrawBehind {
                val p = state.fade.value; val f = state.front; val b = state.back   // draw-phase reads
                drawRect(fallback)
                b?.let { drawImage(it.sharp, dstSize = dst, alpha = backAlpha(f, p), filterQuality = FilterQuality.Low) }
                f?.let { drawImage(it.sharp, dstSize = dst, alpha = p,               filterQuality = FilterQuality.Low) }
                val luma = lerp(b?.luma ?: 0f, f?.luma ?: 0f, p)
                drawRect(Brush.verticalGradient(0f to Haku.night.copy(alpha = scrimAlpha(luma, top = true)),
                                                1f to Haku.night.copy(alpha = scrimAlpha(luma, top = false))))
            }
        })
}
```

## Frost modifier (per card)

```kotlin
class FrostOrigin { var pos by mutableStateOf(Offset.Zero) }

fun Modifier.frost(bd: BackdropState?, origin: FrostOrigin, radius: Dp): Modifier =
    if (bd == null) this else this
        .onPlaced { origin.pos = it.positionInRoot() }          // fires on (re)placement only
        .drawWithCache {
            val clip = Path().apply { addRoundRect(RoundRect(size.toRect(), CornerRadius(radius.toPx()))) }
            val dst = IntSize(size.width.roundToInt(), size.height.roundToInt())
            onDrawBehind {
                val root = bd.rootSize
                val f = bd.front; val b = bd.back
                if (root.width == 0 || (f == null && b == null)) return@onDrawBehind
                val p = bd.fade.value                          // draw-phase read: no recomposition
                clipPath(clip) {
                    b?.let { frostCrop(it.soft, origin.pos, root, dst, backAlpha(f, p)) }
                    f?.let { frostCrop(it.soft, origin.pos, root, dst, p) }
                }
            }
        }

private fun DrawScope.frostCrop(img: ImageBitmap, pos: Offset, root: IntSize, dst: IntSize, alpha: Float) {
    val kx = img.width / root.width.toFloat()        // 256/1024 = 0.25
    val ky = img.height / root.height.toFloat()      // 150/600  = 0.25
    val sx = (pos.x * kx).roundToInt().coerceIn(0, img.width - 1)
    val sy = (pos.y * ky).roundToInt().coerceIn(0, img.height - 1)
    val sw = (dst.width * kx).roundToInt().coerceIn(1, img.width - sx)
    val sh = (dst.height * ky).roundToInt().coerceIn(1, img.height - sy)
    drawImage(img, srcOffset = IntOffset(sx, sy), srcSize = IntSize(sw, sh),
              dstOffset = IntOffset.Zero, dstSize = dst, alpha = alpha,
              filterQuality = FilterQuality.Low)          // bilinear
}
```

**Notes**
- Pass `State<Float>` objects (not `by` delegates) into draw lambdas, so the reads stay in the draw phase.
- Apply the burn-in shift with `Modifier.offset { }` (layout), **not** `graphicsLayer { translationX }`. A layer transform doesn't re-run `onPlaced`, so the frost would desync.

## GlassCard skeleton

```kotlin
@Composable
fun GlassCard(chrome: CardChrome, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val bd = LocalBackdrop.current
    val origin = remember { FrostOrigin() }
    val act   = animateFloatAsState(if (chrome.active && !chrome.stale) 1f else 0f, tween(if (chrome.active) 600 else 1200), label = "act")
    val alert = animateFloatAsState(if (chrome.alert && !chrome.stale) 1f else 0f, tween(600), label = "alert")
    val ring  = rememberPulse(chrome.pulseSeq, chrome.pulseCount)            // Task 18
    Box(modifier
        .frost(bd, origin, 20.dp)
        .drawWithCache { /* build rim path + glow brush */ onDrawWithContent {
            /* night tint 0.55; glow by act.value; rim lerp(ink 0.08 → accent 0.85) by act.value; coral 2dp by alert.value; ring by ring.value */
            drawContent()
        } }
    ) { Column(Modifier.graphicsLayer { alpha = if (chrome.stale) 0.5f else 1f }.padding(start = 14.dp, end = 14.dp, top = 14.dp, bottom = 12.dp)) { content() } }
}
```

## Loader

```kotlin
class BackdropLoader(private val source: HubSource, private val decoder: PhotoDecoder,
                     random: Random = Random.Default, private val clock: () -> Long = System::currentTimeMillis) {
    private val _photo = MutableStateFlow<Photo?>(null)
    val photo: StateFlow<Photo?> = _photo.asStateFlow()
    private val bag = ShuffleBag<String>(random)

    suspend fun run(settings: Flow<BgSettings?>, night: Flow<Boolean>) =
        combine(settings, night) { s, n -> s?.takeIf { it.enabled && !n } }
            .distinctUntilChanged()
            .collectLatest { s ->
                if (s == null) { _photo.value = null; return@collectLatest }
                var listedAt = Long.MIN_VALUE / 2; var misses = 0
                while (true) {
                    if (bag.isEmpty || clock() - listedAt >= LIST_EVERY_MS) {
                        (source.backgrounds() as? Fetch.Ok)?.let { bag.reset(it.value); listedAt = clock() }
                    }
                    val next = bag.next()?.let { load(it) }
                    when {
                        next != null -> { _photo.value = next; misses = 0 }
                        bag.isEmpty  -> _photo.value = null
                        else         -> misses++
                    }
                    delay(if (next != null) s.intervalMs.coerceAtLeast(60_000) else 60_000L * misses.coerceIn(1, 5))
                }
            }

    private suspend fun load(name: String): Photo? = withContext(Dispatchers.IO) {
        try {
            val sharpB = (source.background(name, 1024, 600, "cover", 0) as? Fetch.Ok)?.value ?: return@withContext null
            val softB  = (source.background(name, 256, 150, "cover", 8) as? Fetch.Ok)?.value ?: return@withContext null
            val (soft, luma) = decoder.soft(softB) ?: return@withContext null
            val sharp = decoder.sharp(sharpB) ?: return@withContext null
            Photo(sharp, soft, luma)
        } catch (e: Exception) { null } catch (e: OutOfMemoryError) { null }
    }
    companion object { const val LIST_EVERY_MS = 10 * 60_000L }
}

/** 0..1; max(whole frame, header band): the clock sits on bare photo + scrim. */
fun meanLuma(argb: IntArray, width: Int, topRows: Int): Float {
    if (argb.isEmpty()) return 0f
    var all = 0.0; var top = 0.0; val topN = minOf(argb.size, topRows * width)
    for (i in argb.indices) {
        val c = argb[i]
        val y = 0.2126 * ((c shr 16) and 0xFF) + 0.7152 * ((c shr 8) and 0xFF) + 0.0722 * (c and 0xFF)
        all += y; if (i < topN) top += y
    }
    return (maxOf(all / argb.size, top / topN) / 255.0).toFloat()
}

class ShuffleBag<T>(private val random: Random) {
    private var items = emptyList<T>(); private val queue = ArrayDeque<T>(); private var last: T? = null
    val isEmpty get() = items.isEmpty()
    fun reset(newItems: List<T>) { if (newItems.toSet() != items.toSet()) { items = newItems; queue.clear() } }
    fun next(): T? {
        if (items.isEmpty()) return null
        while (true) {
            if (queue.isEmpty()) items.shuffled(random).toMutableList().also {
                if (it.size > 1 && it.first() == last) it.add(it.removeAt(0)); queue.addAll(it) }
            val n = queue.removeFirst()
            if (n in items) return n.also { last = it }
        }
    }
}
```

**Android decoding**
- **sharp:** `BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.HARDWARE }`. Fall back to a plain decode plus `prepareToDraw()`, then `asImageBitmap()`.
- **soft:** a plain ARGB_8888 decode. Read its pixels with `getPixels` for `meanLuma(px, w, topRows = (h * 56 / 600).coerceAtLeast(1))`.
- **No `recycle()`.**

## Pulse

```kotlin
@Composable fun rememberPulse(seq: Int, count: Int): State<Float> {
    val ring = remember { Animatable(0f) }
    var seen by remember { mutableIntStateOf(seq) }
    LaunchedEffect(seq) {
        if (seq == seen) return@LaunchedEffect
        seen = seq
        repeat(count) { ring.snapTo(0f); ring.animateTo(1f, tween(1400, easing = FastOutSlowInEasing)) }
        ring.snapTo(0f)
    }
    return ring.asState()
}
```
