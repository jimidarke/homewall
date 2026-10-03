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

' --- Smoked-glass palette (v0.7, 0xRRGGBBAA) ----------------------------
' Dark translucent surfaces that sit over the rotating photo background.
' Alpha (low byte) is deliberate: cards ~80%, focused ~90%, text chips ~85%,
' the full-screen dim scrim ~50%. Light text on top; brand/severity accents
' (HK_BRAND/hkSeverityColor) stay for the ring + stripe.
function HK_GLASS_CARD()       as string : return "0x1A211FCC" : end function  ' card at rest
function HK_GLASS_CARD_FOCUS() as string : return "0x2A3532E6" : end function  ' focused card (brighter)
function HK_GLASS_CHIP()       as string : return "0x0C1211D9" : end function  ' chip behind label text
function HK_GLASS_DIM()        as string : return "0x0A0E0D80" : end function  ' scrim over the photo
function HK_GLASS_PANEL()      as string : return "0x121816F2" : end function  ' diag panel body (~95%)
function HK_TEXT_LIGHT_MUTED() as string : return "0xF3EFE6B3" : end function  ' secondary light text

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

' Rolling agenda tile (timeline): per-window dwell before advancing. Descriptor
' may override via tile.rotateMs; floored so a tiny value can't thrash.
function HK_TILE_ROTATE_MS()     as integer : return 4000 : end function
function HK_TILE_ROTATE_MIN_MS() as integer : return 1500 : end function

' Home-tile accent icon (weather/energy/water): fetched supersampled, shown
' large in the card body beside the hero value — see ModuleTile.brs::layout/paintIcon.
function HK_TILE_ICON_PX()         as integer : return 168 : end function
function HK_TILE_ICON_DISPLAY_PX() as integer : return 140 : end function

' Rotating background gallery (v0.7). Interval is overridable per-install via
' /api/config's `background.intervalMs`; hkBgRotateMs() resolves it with a floor.
function HK_BG_ROTATE_MS()    as integer : return 20000 : end function  ' default dwell per image
function HK_BG_ROTATE_MIN_MS() as integer : return 5000 : end function  ' floor (avoid decode thrash)
function HK_BG_CROSSFADE_MS() as integer : return 800   : end function  ' photo dissolve duration

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
function HK_REG_KEY_CONFIG()        as string : return "hubConfigV2"         : end function
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

' --- Generic card-grid geometry + navigation (HomeGroup, generalized GRID) ---
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

' D-pad move over a row-major cols x rows grid: returns the new flat index,
' clamped at the edges (no wrap). Generalizes GridGroup's hardcoded 2x2 ladder.
function hkGridNeighbor(idx as integer, key as string, cols as integer, rows as integer) as integer
    if cols < 1 then cols = 1
    if rows < 1 then rows = 1
    col = idx mod cols
    row = idx \ cols
    if key = "left"  and col > 0        then col = col - 1
    if key = "right" and col < cols - 1 then col = col + 1
    if key = "up"    and row > 0        then row = row - 1
    if key = "down"  and row < rows - 1 then row = row + 1
    return row * cols + col
end function

' --- Agenda helpers (timeline / calendar tiles + drill) ------------------
' Items arrive from the sidecar as an array of assocarrays, each carrying a
' `kind` ("event" | "header"). Pure + unit-tested so the rolling/window logic
' stays off the SceneGraph thread and testable via the brs CLI.

' Keep only the event rows (drop "header" dividers) — the rolling tile shows a
' window of these; the drill renders headers + events verbatim.
function hkAgendaEventRows(items as object) as object
    out = []
    if items = invalid then return out
    for each it in items
        if it <> invalid then
            k = it.kind
            if k <> invalid and k = "event" then out.push(it)
        end if
    end for
    return out
end function

' A wrapping window of `size` items starting at `offset` (rolling tile). Returns
' items in order, wrapping past the end. Empty/size<=0 -> []; size>=count returns
' each item once starting at offset (no duplicates).
function hkAgendaWindow(items as object, offset as integer, size as integer) as object
    out = []
    if items = invalid then return out
    n = items.count()
    if n = 0 or size <= 0 then return out
    take = size
    if take > n then take = n
    if offset < 0 then offset = 0
    for i = 0 to take - 1
        out.push(items[(offset + i) mod n])
    end for
    return out
end function

' Source array for a STATIC (non-rotating) agenda tile: the full items list
' (headers + events) by default, matching the calendar tile's TODAY/TOMORROW
' context — or just the event rows when dropHeaders is set, for a card like
' Recent Activity where a header would just eat one of the few visible slots
' without telling you anything the per-row relative time doesn't already.
function hkAgendaStaticSource(items as object, ev as object, dropHeaders as boolean) as object
    if dropHeaders then return ev
    return items
end function

' Resolve a rolling tile's per-window dwell (ms) from the descriptor's
' tile.rotateMs, floored. Missing/invalid -> default. Pure/testable.
function hkTileRotateMs(tdef as object) as integer
    ms = HK_TILE_ROTATE_MS()
    if tdef <> invalid and tdef.rotateMs <> invalid then
        v = hkParseInt(tdef.rotateMs)
        if v > 0 then ms = v
    end if
    if ms < HK_TILE_ROTATE_MIN_MS() then ms = HK_TILE_ROTATE_MIN_MS()
    return ms
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
