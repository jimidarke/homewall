' HAku — config / constants / registry helpers.
'
' BrightScript has no module-scope const declaration, so each token is exposed
' as a function returning the literal value. Cheap call, easy to grep.

' --- Daylight palette (0xRRGGBBAA) ---------------------------------------
function HK_BG_CREAM()    as string : return "0xF7F1E3FF" : end function
function HK_BG_WARM()     as string : return "0xECE3D0FF" : end function
function HK_BG_SCRIM()    as string : return "0x2B2A26CC" : end function
function HK_TEXT_INK()    as string : return "0x2B2A26FF" : end function
function HK_TEXT_CREAM()  as string : return "0xFAF6EEFF" : end function
function HK_TEXT_MUTED()  as string : return "0x2B2A2699" : end function
function HK_BRAND()       as string : return "0x5B8C7FFF" : end function
function HK_LIVE()        as string : return "0xD4673EFF" : end function
function HK_WARN()        as string : return "0xD9A441FF" : end function
function HK_OK()          as string : return "0x6B9080FF" : end function

' --- Glass palette (the tablet's v3 tokens; 0xRRGGBBAA) ------------------
' The home screen is the tablet's smoked glass without the frost: rounded 9-patch
' cards (images/glass/, scripts/gen_glass_assets.py) tinted night over the photo.
' HK_GLASS_PANEL / HK_TEXT_LIGHT_MUTED stay for the diag and drill screens.
function HK_GLASS_CARD_FOCUS() as string : return "0x2A3532E6" : end function  ' drill/diag focus fill
function HK_GLASS_PANEL()      as string : return "0x121816F2" : end function  ' diag panel body (~95%)
function HK_TEXT_LIGHT_MUTED() as string : return "0xF3EFE6B3" : end function  ' secondary light text

function HK_INK()        as string : return "0xFAF6EEFF" : end function
function HK_INK_MUTED()  as string : return "0xFAF6EEC7" : end function  ' ink at 78%
function HK_INK_FAINT()  as string : return "0xFAF6EE7A" : end function  ' ink at 48%
function HK_NIGHT()      as string : return "0x0C1211FF" : end function
function HK_SAGE()       as string : return "0x5B8C7FFF" : end function
function HK_CORAL()      as string : return "0xD4673EFF" : end function
function HK_AMBER()      as string : return "0xD9A441FF" : end function
function HK_OFFLINE()    as string : return "0x6E7471FF" : end function
function HK_WATER()      as string : return "0x4FB3E8FF" : end function
function HK_HEAT()       as string : return "0xF2994AFF" : end function
function HK_COOL()       as string : return "0x7CCBF2FF" : end function
function HK_WASHER()     as string : return "0x00AAFFFF" : end function
function HK_DRYER()      as string : return "0xFF6900FF" : end function
function HK_LED_IDLE()   as string : return "0xE5484DFF" : end function
function HK_LED_STALE()  as string : return "0x9B7BEAFF" : end function

' Card tint strength over a sharp photo (the tablet's frosted glass gets by with
' 0.32-0.48; with no blur behind it, 0.55 still let busy photos crowd small muted text).
function HK_GLASS_FILL_OPACITY() as float : return 0.62 : end function
function HK_LIT_RIM_OPACITY()    as float : return 0.85 : end function
function HK_GLOW_OPACITY()       as float : return 0.18 : end function
function HK_CHIP_LIT_OPACITY()   as float : return 0.28 : end function
function HK_STALE_OPACITY()      as float : return 0.5  : end function
function HK_OFFLINE_OPACITY()    as float : return 0.45 : end function

' The display layout this channel asks the sidecar for (`?layout=`).
function HK_LAYOUT() as string : return "roku" : end function

' Agenda row heights (px): the tablet's 22 / 26 dp at the Roku's type scale. Activity
' rows are one line on the 0.12 wall (2x2 card): glyph, title, sub, time.
function HK_ROW_ACTIVITY() as integer : return 40 : end function
function HK_ROW_DAY()      as integer : return 32 : end function
function HK_ROW_EVENT()    as integer : return 38 : end function

' Animation durations (ms)
function HK_FADE_MS()         as integer : return 200 : end function
function HK_HUD_SLIDE_MS()    as integer : return 180 : end function
function HK_CROSSFADE_MS()    as integer : return 220 : end function
function HK_TOAST_IN_MS()     as integer : return 180 : end function
function HK_TOAST_OUT_MS()    as integer : return 150 : end function
function HK_OVERLAY_SLIDE_MS() as integer : return 200 : end function

' Dashboard/home timings.
function HK_STATE_POLL_MS()   as integer : return 10000  : end function  ' sidecar /api/state poll
function HK_IDLE_TO_HOME_MS() as integer : return 300000 : end function  ' user idle -> glance home
function HK_RETURN_HOME_MS()  as integer : return 60000  : end function  ' after an auto-takeover
function HK_HOME_CAM_MAX_MS() as integer : return 900000 : end function  ' homeCam= override, if HA's revert never arrives

' Rotating background gallery. Interval is overridable per-install via
' /api/config's `background.intervalMs`; hkBgRotateMs() resolves it with a floor.
function HK_BG_ROTATE_MS()    as integer : return 20000 : end function  ' default dwell per image
function HK_BG_ROTATE_MIN_MS() as integer : return 5000 : end function  ' floor (avoid decode thrash)
function HK_BG_CROSSFADE_MS() as integer : return 800   : end function  ' photo dissolve duration
function HK_BG_LIST_MS()      as integer : return 600000 : end function  ' photo list refresh (tablet LIST_EVERY_MS)

' Overlay default time-to-live, by kind. Caller may override via `dwell=` (sec)
' or `duration=` (sec) in the ECP /input payload.
function HK_OVERLAY_PIP_MS()     as integer : return 30000 : end function
function HK_OVERLAY_DOOR_MS()    as integer : return 6000  : end function
function HK_OVERLAY_WEATHER_MS() as integer : return 10000 : end function
function HK_OVERLAY_SENSOR_MS()  as integer : return 8000  : end function
function HK_OVERLAY_TEXT_MS()    as integer : return 4000  : end function

' Default discovery server base for the JPEG snapshot endpoint. Discovery may
' override this at runtime once the SSDP payload lands; the constant keeps the
' PIP usable on a cold launch before discovery completes.
function HK_OVERLAY_PIP_INTERVAL_MS() as integer : return 500 : end function
function HK_OVERLAY_SNAPSHOT_BASE() as string : return "http://192.0.2.20:1984" : end function

' Resolve a per-overlay-kind duration. Honours user-supplied `dwell` (seconds)
' or `duration` (seconds) on the params; falls back to the kind's HK_OVERLAY_*_MS
' default. Pure helper, exercised by tests.
function hkOverlayDurationMs(kind as string, params as object) as integer
    overrideSec = 0
    if params <> invalid then
        if params.duration <> invalid then overrideSec = hkParseInt(params.duration)
        if overrideSec = 0 and params.dwell <> invalid then overrideSec = hkParseInt(params.dwell)
    end if
    if overrideSec > 0 then return overrideSec * 1000
    if kind = "pip"     then return HK_OVERLAY_PIP_MS()
    if kind = "door"    then return HK_OVERLAY_DOOR_MS()
    if kind = "weather" then return HK_OVERLAY_WEATHER_MS()
    if kind = "sensor"  then return HK_OVERLAY_SENSOR_MS()
    if kind = "text"    then return HK_OVERLAY_TEXT_MS()
    return HK_OVERLAY_TEXT_MS()
end function

' Severity → border colour. Mirrors Toast.brs's mapping so visual language is
' consistent across overlays. Pure helper, tested.
function hkSeverityColor(severity as string) as string
    if severity = "high" or severity = "live" then return HK_LIVE()
    if severity = "low"  or severity = "ok"   then return HK_OK()
    return HK_WARN()  ' "normal" / "warn" / unset
end function

' --- Camera roster -------------------------------------------------------
' Order = clockwise perimeter (front-of-house first). Indices match the
' GRID 2x2 layout: 0=top-left, 1=top-right, 2=bottom-left, 3=bottom-right.
function HK_CAMS() as object
    return ["front", "yard", "side", "backyard"]
end function

function HK_CAM_DISPLAY_NAME(cam as string) as string
    if cam = "front"    then return "Front Door"
    if cam = "front_steps" then return "Front Steps"
    if cam = "yard"     then return "Yard"
    if cam = "side"     then return "Side"
    if cam = "backyard" then return "Backyard"
    if cam = "mosaic"   then return "Grid"
    return cam
end function

' --- Module registry -----------------------------------------------------
' The Roku twin of the sidecar's modules/__init__.MODULES table. Maps a module
' `kind` to how its home-page tile renders and what its drill-down is, so the
' channel can lay out and route a module even before /api/config arrives.
' tileType: value | chart | image | camera | agenda   (unknown -> neutral tile)
' drill:    chart | camera | agenda | image            (camera reuses LiveGroup)
function HK_MODULE_KINDS() as object
    return {
        weather:  { tileType: "value",  drill: "chart"  }
        cameras:  { tileType: "camera", drill: "camera" }
        energy:   { tileType: "value",  drill: "chart"  }
        water:    { tileType: "value",  drill: "chart"  }
        gas:      { tileType: "value",  drill: "value"  }
        climate:  { tileType: "value",  drill: "value"  }
        doors:    { tileType: "value",  drill: "agenda" }
        laundry:  { tileType: "value",  drill: "value"  }
        motion:   { tileType: "value",  drill: "camera" }
        calendar: { tileType: "agenda", drill: "agenda" }
        timeline: { tileType: "agenda", drill: "agenda" }
        timers:   { tileType: "agenda", drill: "agenda" }
    }
end function

' Look up a kind's descriptor; unknown kinds fall back to a neutral value tile
' (forward-compat: a newer sidecar can ship a kind this build doesn't know).
function hkModuleKind(kind as string) as object
    kinds = HK_MODULE_KINDS()
    if kind <> invalid and kinds.doesExist(kind) then return kinds[kind]
    return { tileType: "value", drill: "agenda" }
end function

' --- Registry ------------------------------------------------------------
' All registry keys live under section "haku". Bump CACHE_VER whenever
' the discovery payload schema changes so old caches are ignored.
function HK_REG_SECTION()      as string  : return "haku" : end function
function HK_REG_CACHE_VER()    as integer : return 2 : end function

function HK_REG_KEY_DEFAULT_CAM()   as string : return "defaultCam"          : end function
function HK_REG_KEY_DISCOVERY()     as string : return "discoveryCacheV2"    : end function
function HK_REG_KEY_HA_URL()        as string : return "haUrl"               : end function
function HK_REG_KEY_HA_TOKEN()      as string : return "haToken"             : end function
function HK_REG_KEY_AUDIO_PREFIX()  as string : return "audioMuted_"         : end function
function HK_REG_KEY_CONFIG()        as string : return "hubConfigRokuV1"     : end function
' The pre-0.11 default-view config cache; deleted once on boot (a 4x2 grid
' drawn with the 6x3 geometry would be wrong, and the slot is better freed).
function HK_REG_KEY_CONFIG_OLD()    as string : return "hubConfigV2"         : end function
function HK_REG_KEY_HUB_BASE()      as string : return "hubBaseV2"           : end function

function regRead(key as string) as string
    section = createObject("roRegistrySection", HK_REG_SECTION())
    if section = invalid then return ""
    if not section.exists(key) then return ""
    return section.read(key)
end function

sub regWrite(key as string, value as string)
    section = createObject("roRegistrySection", HK_REG_SECTION())
    if section = invalid then return
    section.write(key, value)
    section.flush()
end sub

sub regDelete(key as string)
    section = createObject("roRegistrySection", HK_REG_SECTION())
    if section = invalid then return
    if section.exists(key) then
        section.delete(key)
        section.flush()
    end if
end sub

' --- Pure helpers (also exercised by tests/unit) -------------------------

' Exponential backoff schedule for stream reconnects: 2s, 5s, 10s, 30s, 30s…
function hkNextBackoffSeconds(attempt as integer) as integer
    if attempt <= 1 then return 2
    if attempt = 2 then return 5
    if attempt = 3 then return 10
    return 30
end function

' The HLS URL discovery gives `cam`, else the mosaic's (a partial payload), else "".
function hkStreamUrl(streams as dynamic, cam as string) as string
    if streams = invalid or type(streams) <> "roAssociativeArray" then return ""
    s = streams[cam]
    if s <> invalid and s.hls <> invalid then return s.hls
    if streams.mosaic <> invalid and streams.mosaic.hls <> invalid then return streams.mosaic.hls
    return ""
end function

' The camera a camera tile shows: tile.cam (0.12), else the 0.10 thumbnail's thumbCam,
' else the mosaic.
function hkTileCam(tile as dynamic) as string
    if tile = invalid or type(tile) <> "roAssociativeArray" then return "mosaic"
    if tile.cam <> invalid and tile.cam <> "" then return tile.cam.toStr()
    if tile.thumbCam <> invalid and tile.thumbCam <> "" then return tile.thumbCam.toStr()
    return "mosaic"
end function

' The camera the home square plays: HA's homeCam= override when discovery has an HLS
' stream for it, else the tile's own camera. Checking the stream here keeps hkStreamUrl's
' mosaic fallback from turning an unknown override into the grid.
function hkHomeCam(tile as dynamic, override as dynamic, streams as dynamic) as string
    if override <> invalid and override <> "" and streams <> invalid and type(streams) = "roAssociativeArray" then
        s = streams[override]
        if s <> invalid and s.hls <> invalid then return override.toStr()
    end if
    return hkTileCam(tile)
end function

' Index of `cam` in roster; returns 0 if not found (safe default for carousel).
function hkCamIndex(cam as string, roster as object) as integer
    for i = 0 to roster.count() - 1
        if roster[i] = cam then return i
    end for
    return 0
end function

' Parse anything-int-ish to integer; invalid/empty → 0.
function hkParseInt(v as dynamic) as integer
    if v = invalid then return 0
    if type(v) = "Integer" then return v
    if type(v) = "roInt" then return v
    return v.toStr().toInt()
end function

' Return [x, y] top-left of the focused 960x540 quadrant in the 2x2 grid.
'   0=TL  1=TR  2=BL  3=BR
function hkGridQuadrantPos(idx as integer) as object
    if idx = 1 then return [960, 0]
    if idx = 2 then return [0, 540]
    if idx = 3 then return [960, 540]
    return [0, 0]
end function

' --- Card-grid geometry (HomeGroup) -------------------------------------
' Pixel rect for a tile spanning (wspan x hspan) cells at (col,row) in a grid
' described by { cellW, cellH, originX, originY, gap }. Pure + unit-tested.
function hkTileRect(col as integer, row as integer, wspan as integer, hspan as integer, grid as object) as object
    cellW = hkNumOr(grid, "cellW", 600)
    cellH = hkNumOr(grid, "cellH", 440)
    gap   = hkNumOr(grid, "gap", 24)
    ox    = hkNumOr(grid, "originX", 60)
    oy    = hkNumOr(grid, "originY", 160)
    if wspan < 1 then wspan = 1
    if hspan < 1 then hspan = 1
    return {
        x: ox + col * (cellW + gap)
        y: oy + row * (cellH + gap)
        w: wspan * cellW + (wspan - 1) * gap
        h: hspan * cellH + (hspan - 1) * gap
    }
end function

' The largest 16:9 frame inside a bw x bh body, centred: { x, y, w, h }.
function hkVideoFit(bw as integer, bh as integer) as object
    w = bw
    h = Int(bw * 9 / 16)
    if h > bh then
        h = bh
        w = Int(bh * 16 / 9)
    end if
    return { x: (bw - w) \ 2, y: (bh - h) \ 2, w: w, h: h }
end function

' Small assoc-array numeric accessor with a default (grids arrive from JSON).
function hkNumOr(obj as object, key as string, default as integer) as integer
    if obj = invalid then return default
    if not obj.doesExist(key) then return default
    return hkParseInt(obj[key])
end function

' Format a "motion N min/h ago" string from a unix-seconds timestamp.
' nowSec is passed in so the function stays pure and testable.
function hkMotionLabel(ts as integer, nowSec as integer) as string
    if ts <= 0 then return "no recent motion"
    age = nowSec - ts
    if age < 60 then return "motion just now"
    if age < 3600 then return "motion " + (age / 60).toStr() + " min ago"
    return "motion " + (age / 3600).toStr() + "h ago"
end function

' Next index in a wrapping ring of `count` items. Drives the background gallery
' rotation and stays pure so tests/unit can cover the wrap. count<=0 -> 0.
function hkBgNextIndex(idx as integer, count as integer) as integer
    if count <= 0 then return 0
    return (idx + 1) mod count
end function

' How the gallery takes a refreshed photo list (`nxt`) while showing `shown` from `cur`:
'   first  nothing yet: start from photo 0
'   empty  nothing yet and nothing now: the fallback image
'   keep   a failed or empty refresh: carry on with the photos it has
'   same   nothing changed
'   swap   a changed list: carry on from where it was; idx is the shown photo's place
'          in the new list, or the last place when it went, so the next is the first
function hkBgListUpdate(cur as object, nxt as object, shown as string) as object
    if nxt.count() = 0 then
        if cur.count() = 0 then return { action: "empty", idx: 0 }
        return { action: "keep", idx: 0 }
    end if
    if cur.count() = 0 then return { action: "first", idx: 0 }
    same = (cur.count() = nxt.count())
    if same then
        for i = 0 to cur.count() - 1
            if cur[i] <> nxt[i] then
                same = false
                exit for
            end if
        end for
    end if
    if same then return { action: "same", idx: 0 }
    idx = nxt.count() - 1
    for i = 0 to nxt.count() - 1
        if nxt[i] = shown then
            idx = i
            exit for
        end if
    end for
    return { action: "swap", idx: idx }
end function

' Resolve the background rotate interval (ms) from /api/config, floored so a
' misconfigured tiny value can't thrash the decoder. Missing/invalid -> default.
function hkBgRotateMs(cfg as object) as integer
    ms = HK_BG_ROTATE_MS()
    if cfg <> invalid and cfg.background <> invalid then
        v = hkParseInt(cfg.background.intervalMs)
        if v > 0 then ms = v
    end if
    if ms < HK_BG_ROTATE_MIN_MS() then ms = HK_BG_ROTATE_MIN_MS()
    return ms
end function

' Human "N ago" from a unix-seconds timestamp, for the diagnostic screen.
' nowSec passed in so the helper stays pure/testable. ts<=0 -> "never".
function hkAgeLabel(nowSec as integer, ts as integer) as string
    if ts <= 0 then return "never"
    age = nowSec - ts
    if age < 0 then age = 0
    if age < 5 then return "just now"
    if age < 60 then return age.toStr() + "s ago"
    if age < 3600 then return (age \ 60).toStr() + " min ago"
    if age < 86400 then return (age \ 3600).toStr() + "h ago"
    return (age \ 86400).toStr() + "d ago"
end function

' Compact device-uptime label ("2d 3h" / "3h 12m" / "12m") from milliseconds.
' Kept pure so tests/unit can cover it; roDeviceInfo returns a LongInteger.
function hkUptimeLabel(ms as longinteger) as string
    if ms <= 0 then return "—"
    secs = ms \ 1000
    days = secs \ 86400
    hrs  = (secs mod 86400) \ 3600
    mins = (secs mod 3600) \ 60
    if days > 0 then return days.toStr() + "d " + hrs.toStr() + "h"
    if hrs  > 0 then return hrs.toStr() + "h " + mins.toStr() + "m"
    return mins.toStr() + "m"
end function

' --- Glass home helpers (ports of the tablet's pure functions) ---------------

' How fresh the last good /api/state is: "live" (<= 30 s), "lagging" (<= 2 min) or
' "offline". Never fetched (lastOkSec 0) is offline. Tablet: ui/Layout.kt freshness.
function hkFreshness(lastOkSec as integer, nowSec as integer) as string
    if lastOkSec <= 0 then return "offline"
    age = nowSec - lastOkSec
    if age <= 30 then return "live"
    if age <= 120 then return "lagging"
    return "offline"
end function

' Whether the wall shows itself offline: only once a state fetch has finished, so a
' cold start never flashes offline before it has tried.
function hkOfflineShown(fresh as string, fetched as boolean) as boolean
    return fetched and fresh = "offline"
end function

' The header's status word and dot colour (tablet Header.kt headerStatus). `degraded`
' is the titles of stale cards in config order; past two it counts them.
function hkHeaderStatus(fresh as string, fetched as boolean, degraded as object) as object
    if not fetched then return { label: "connecting", dot: HK_OFFLINE() }
    if fresh = "offline" then return { label: "offline", dot: HK_OFFLINE() }
    if fresh = "lagging" then return { label: "lagging", dot: HK_AMBER() }
    if degraded <> invalid and degraded.count() > 0 then
        names = degraded.count().toStr()
        if degraded.count() <= 2 then names = degraded.join(", ")
        return { label: "degraded · " + names, dot: HK_AMBER() }
    end if
    return { label: "live", dot: HK_SAGE() }
end function

' "9:17 PM" from a 24 h hour and minute.
function hkClockLabel(h as integer, mm as integer) as string
    ampm = "AM"
    if h >= 12 then ampm = "PM"
    h12 = h mod 12
    if h12 = 0 then h12 = 12
    mmStr = mm.toStr()
    if mm < 10 then mmStr = "0" + mmStr
    return h12.toStr() + ":" + mmStr + " " + ampm
end function

' "Wednesday, October 7" (roDateTime's GetWeekday() gives the day name).
function hkDateLabel(weekday as string, month as integer, day as integer) as string
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    if month < 1 or month > 12 then return weekday
    return weekday + ", " + months[month - 1] + " " + day.toStr()
end function

' Burn-in shift [dx, dy] in px: each 10-minute slot of the wall clock takes the next of
' 8 positions on a +-2 px square ring, so each step moves 2 px on one axis (BurnIn.kt).
function hkBurnIn(epochSec as integer) as object
    ring = [[-2, -2], [0, -2], [2, -2], [2, 0], [2, 2], [0, 2], [-2, 2], [-2, 0]]
    slot = epochSec \ 600
    return ring[slot mod 8]
end function

' The glyph a card draws: `glyph` if this build ships it, else the kind's default, else
' "" (Glyphs.kt nameFor). Needs Glyphs.brs (HK_GLYPHS) loaded beside this file.
function hkGlyphFor(glyph as dynamic, kind as dynamic) as string
    shipped = HK_GLYPHS()
    if glyph <> invalid and shipped.doesExist(glyph.toStr()) then return glyph.toStr()
    defaults = {
        doors: "door", laundry: "washing-machine", water: "water-outline", energy: "flash",
        gas: "meter-gas", climate: "thermostat", weather: "weather-partly-cloudy",
        calendar: "calendar", timeline: "history", cameras: "cctv"
    }
    if kind <> invalid and defaults.doesExist(kind.toStr()) then return defaults[kind.toStr()]
    return ""
end function

' A card's accent from its glyph (Tokens.kt accentFor).
function hkAccentFor(glyph as string) as string
    if glyph = "door-open" then return HK_AMBER()
    if glyph = "water" then return HK_WATER()
    if glyph = "fire" then return HK_HEAT()
    if glyph = "snowflake" then return HK_COOL()
    if glyph = "washing-machine" then return HK_WASHER()
    if glyph = "tumble-dryer" then return HK_DRYER()
    return HK_SAGE()
end function

' An Activity row's accent from its glyph (Tokens.kt itemAccent).
function hkItemAccent(glyph as string) as string
    if glyph = "door-open" or glyph = "lock-open-variant" then return HK_AMBER()
    if glyph = "home-account" then return HK_SAGE()
    return HK_INK_MUTED()
end function

' "#RRGGBB" / "#AARRGGBB" / "0xRRGGBBAA" -> "0xRRGGBBAA"; anything else -> fallback.
function hkHexToRoku(s as dynamic, fallback as string) as string
    if s = invalid then return fallback
    v = UCase(s.toStr())
    if Left(v, 1) = "#" then
        digits = Mid(v, 2)
        if not hkIsHex(digits) then return fallback
        if Len(digits) = 6 then return "0x" + digits + "FF"
        if Len(digits) = 8 then return "0x" + Mid(digits, 3) + Left(digits, 2)
        return fallback
    end if
    if Left(v, 2) = "0X" and Len(v) = 10 and hkIsHex(Mid(v, 3)) then return "0x" + Mid(v, 3)
    return fallback
end function

function hkIsHex(s as string) as boolean
    if Len(s) = 0 then return false
    for i = 1 to Len(s)
        if Instr(1, "0123456789ABCDEF", Mid(s, i, 1)) = 0 then return false
    end for
    return true
end function

' Which card a module draws (tablet Project.kt card() + DoorsCard/LaundryCard): doors
' and laundry need a non-empty array, else they are value cards; agenda, camera and
' forecast by tile.type; anything else (an unknown or retired type, like chart) is a
' value card.
function hkCardKind(d as object, values as dynamic) as string
    kind = ""
    if d.kind <> invalid then kind = d.kind.toStr()
    ttype = ""
    if d.tile <> invalid and d.tile.type <> invalid then ttype = d.tile.type.toStr()
    hasVals = (values <> invalid and type(values) = "roAssociativeArray")
    if kind = "doors" and hasVals then
        if type(values.doors) = "roArray" then
            if values.doors.count() > 0 then return "doors"
        end if
    end if
    if kind = "laundry" and hasVals then
        if type(values.machines) = "roArray" then
            if values.machines.count() > 0 then return "laundry"
        end if
    end if
    if ttype = "agenda" or ttype = "camera" or ttype = "forecast" then return ttype
    return "value"
end function

' A value card is stale when the sidecar says so, and also with no tile, a blank hero or
' an `error`: none of those is a reading (tablet Project.kt value()).
function hkTileStale(values as dynamic) as boolean
    if values = invalid or type(values) <> "roAssociativeArray" then return true
    if values.stale = true then return true
    if values.error <> invalid then return true
    t = values.tile
    if t = invalid or type(t) <> "roAssociativeArray" then return true
    if t.hero = invalid then return true
    return (t.hero.toStr().trim() = "")
end function

' An agenda card is stale only when the sidecar says so.
function hkAgendaStale(values as dynamic) as boolean
    if values = invalid or type(values) <> "roAssociativeArray" then return false
    return (values.stale = true)
end function

' Door rows (px): a 64 px row (label and state over the age) and an 8 px gap.
function HK_DOOR_ROW() as integer : return 64 : end function
function HK_DOOR_GAP() as integer : return 8 : end function

' How a doors body lays its rows out: two columns side by side once it is a 2-wide
' card (as LaundryBody does), and as many rows as fit the height.
function hkDoorLayout(bw as integer, bh as integer) as object
    cols = 1
    if bw >= 540 then cols = 2
    rows = (bh + HK_DOOR_GAP()) \ (HK_DOOR_ROW() + HK_DOOR_GAP())
    if rows < 0 then rows = 0
    return { cols: cols, rows: rows }
end function

' The doors a card with room for `fit` rows shows: open and unknown before closed (stable,
' so each group keeps the sidecar's order), at most 3 (DoorsCard.kt doorsShown).
function hkDoorsShown(doors as object, fit as integer) as object
    first = []
    rest = []
    for each d in doors
        if d.state = "closed" then
            rest.push(d)
        else
            first.push(d)
        end if
    end for
    first.append(rest)
    n = fit
    if n > 3 then n = 3
    out = []
    for i = 0 to n - 1
        if i >= first.count() then exit for
        out.push(first[i])
    end for
    return out
end function

' --- The laundry LED bar (LaundryFrames.kt): four segment brightnesses 0..1 ---

' How often an animated bar steps (ms), or 0 when it is static. "stale" is the
' pseudo-mode of a machine HA has no data for.
function hkLedStepMs(mode as string) as integer
    if mode = "overtime" then return 100
    if mode = "done" then return 120
    if mode = "done_calm" then return 450
    if mode = "stale" then return 150
    return 0
end function

' Only an animated mode (or a stale machine's comet) steps, and only while the card
' isn't quiet (the wall offline, or the whole card stale).
function hkLedAnimates(mode as string, machineStale as boolean, quiet as boolean) as boolean
    if quiet then return false
    m_ = mode
    if machineStale then m_ = "stale"
    return hkLedStepMs(m_) > 0
end function

function hkLedFrame(mode as string, leds as integer, tMs as integer, stale as boolean) as object
    f = [0.0, 0.0, 0.0, 0.0]
    pingPong = [0, 1, 2, 3, 2, 1]
    if stale then
        head = (tMs \ 150) mod 4
        f[head] = 1.0
        f[(head + 3) mod 4] = 0.35
        f[(head + 2) mod 4] = 0.1
        return f
    end if
    if mode = "idle" then
        f[0] = 0.25
    else if mode = "running" then
        n = leds
        if n > 4 then n = 4
        for i = 0 to n - 1
            f[i] = 1.0
        end for
    else if mode = "overtime" then
        f[0] = 0.15 + 0.85 * (0.5 + 0.5 * Sin(2 * 3.14159265 * tMs / 2500))
    else if mode = "done" then
        f[pingPong[(tMs \ 120) mod 6]] = 1.0
    else if mode = "done_calm" then
        st = tMs \ 450
        if st > 0 then f[pingPong[(st - 1) mod 6]] = 0.2
        f[pingPong[st mod 6]] = 0.6
    end if
    return f
end function

' The bar's colour: violet while stale, the firmware's dim red while idle, else the
' machine's own colour.
function hkLedColor(mode as string, stale as boolean, machineColor as string) as string
    if stale then return HK_LED_STALE()
    if mode = "idle" then return HK_LED_IDLE()
    return machineColor
end function

' --- Agenda cards (AgendaCard.kt): whole rows only ---------------------------

' How many of `items` fit, in order, in `availPx`; never ends on a day header.
function hkVisibleRowCount(items as object, activity as boolean, availPx as integer) as integer
    used = 0
    n = 0
    for each it in items
        h = HK_ROW_EVENT()
        if activity then
            h = HK_ROW_ACTIVITY()
        else if it.kind = "header" then
            h = HK_ROW_DAY()
        end if
        if used + h > availPx then exit for
        used = used + h
        n = n + 1
    end for
    while n > 0 and items[n - 1].kind = "header"
        n = n - 1
    end while
    return n
end function

' The sidecar's upper-case day header ("WED · OCT 7") as "Wed · Oct 7".
function hkDayLabel(header as string) as string
    words = header.split(" ")
    out = []
    for each w in words
        if Len(w) > 0 then
            out.push(UCase(Left(w, 1)) + LCase(Mid(w, 2)))
        else
            out.push(w)
        end if
    end for
    return out.join(" ")
end function

' --- Sidecar plumbing ----------------------------------------------------------

' `url` with `?layout=<layout>` (or `&layout=`) added; unchanged for "".
function hkWithLayout(url as string, layoutName as string) as string
    if layoutName = invalid or layoutName = "" then return url
    sep = "?"
    if Instr(1, url, "?") > 0 then sep = "&"
    return url + sep + "layout=" + layoutName
end function

' The config as cached in the registry: modules without the keys the channel never reads
' (entities, drill, refreshMs and friends), so it stays well inside the registry slot.
function hkSlimConfig(cfg as object) as object
    out = {}
    for each k in cfg
        if k <> "modules" then out[k] = cfg[k]
    end for
    mods = []
    if cfg.modules <> invalid then
        for each md in cfg.modules
            slim = {}
            for each k in ["id", "kind", "title", "feedKey", "tile", "outlook"]
                if md.doesExist(k) then slim[k] = md[k]
            end for
            mods.push(slim)
        end for
    end if
    out.modules = mods
    return out
end function

' --- Logging -------------------------------------------------------------
sub hkLog(msg as string)
    print "[HAku] " + msg
end sub

sub hkDebug(msg as string)
    #if DEBUG
        print "[HAku][dbg] " + msg
    #end if
end sub

' Structured event log line. Emits a single line of:
'   [HAku] event=<name> k=v k=v
' Keys in `kv` are space-free; values are coerced via toStr() and any spaces
' replaced with `_` so the line stays parseable by tests/smoke.
sub hkEvent(name as string, kv as object)
    line = "[HAku] event=" + name
    if kv <> invalid then
        for each k in kv
            v = kv[k]
            if v = invalid then
                vs = "invalid"
            else
                vs = v.toStr()
            end if
            ' Keep tokens un-greppable
            if LCase(k) = "hatoken" or LCase(k) = "token" or LCase(k) = "password" then
                vs = "*****"
            end if
            line = line + " " + k + "=" + sanitiseForLog(vs)
        end for
    end if
    print line
end sub

function sanitiseForLog(s as string) as string
    out = s
    ' Replace spaces with underscores so key=value parses cleanly.
    out = substituteAll(out, " ", "_")
    return out
end function

function substituteAll(s as string, find as string, repl as string) as string
    if find = "" then return s
    out = ""
    rest = s
    while true
        idx = Instr(1, rest, find)
        if idx = 0 then
            out = out + rest
            exit while
        end if
        out = out + Left(rest, idx - 1) + repl
        rest = Mid(rest, idx + Len(find))
    end while
    return out
end function

function hkNowSeconds() as integer
    d = createObject("roDateTime")
    d.Mark()
    return d.AsSeconds()
end function

' Scrub a key=value query-string-ish blob so haToken (and similar) don't
' end up in the telnet log. Used for printing args / event maps.
function hkScrub(s as string) as string
    out = s
    for each k in ["haToken", "token", "password"]
        idx = Instr(1, LCase(out), LCase(k) + "=")
        if idx > 0 then
            ' Preserve the original key casing from the input by slicing it out.
            origKey = Mid(out, idx, Len(k))
            tail = Mid(out, idx + Len(k) + 1)
            amp = Instr(1, tail, "&")
            if amp > 0 then
                out = Left(out, idx - 1) + origKey + "=*****" + Mid(tail, amp)
            else
                out = Left(out, idx - 1) + origKey + "=*****"
            end if
        end if
    end for
    return out
end function
