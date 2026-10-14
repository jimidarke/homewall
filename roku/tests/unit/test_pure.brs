' tests/unit/test_pure.brs — pure-logic test suite for HAku.
' Run via: npx brs source/Config.brs source/Glyphs.brs tests/unit/test_pure.brs
' (or: npm run test:unit). Exits with the marker line:
'   RESULT pass=<N> fail=<M>
' which the wrapping npm script greps to set the exit code.

sub Main()
    m.pass = 0
    m.fail = 0

    test_hwNextBackoffSeconds()
    test_hwCamIndex()
    test_hwParseInt()
    test_hwGridQuadrantPos()
    test_hwMotionLabel()
    test_hwScrub()
    test_HW_CAMS_roster()
    test_HW_CAM_DISPLAY_NAME()
    test_substituteAll()
    test_hwOverlayDurationMs()
    test_hwSeverityColor()
    test_hkTileRect()
    test_hkTileRect_roku()
    test_hkModuleKind()
    test_hkFreshness()
    test_hkHeaderStatus()
    test_hkClockAndDateLabels()
    test_hkBurnIn()
    test_hkGlyphFor()
    test_hkAccents()
    test_hkHexToRoku()
    test_hkCardKind()
    test_hkTileStale()
    test_hkDoorsShown()
    test_hkLedFrame()
    test_hkLedStepAndColor()
    test_hkVisibleRowCount()
    test_hkDayLabel()
    test_hkWithLayout()
    test_hkSlimConfig()
    test_hkStreamUrl()
    test_hkTileCam()
    test_hkBgListUpdate()
    test_hkVideoFit()
    test_hkDoorLayout()
    test_hkBgNextIndex()
    test_hkBgRotateMs()
    test_hkAgeLabel()
    test_hkUptimeLabel()

    print "RESULT pass=" + m.pass.toStr() + " fail=" + m.fail.toStr()
end sub

sub assertEq(label as string, got as dynamic, want as dynamic)
    g = "(invalid)"
    w = "(invalid)"
    if got <> invalid then g = got.toStr()
    if want <> invalid then w = want.toStr()
    if g = w then
        m.pass = m.pass + 1
        print "  ok    " + label + " = " + g
    else
        m.fail = m.fail + 1
        print "  FAIL  " + label + " got=" + g + " want=" + w
    end if
end sub

sub assertContains(label as string, haystack as string, needle as string)
    if Instr(1, haystack, needle) > 0 then
        m.pass = m.pass + 1
        print "  ok    " + label + " contains " + needle
    else
        m.fail = m.fail + 1
        print "  FAIL  " + label + " missing " + needle + " (haystack=" + haystack + ")"
    end if
end sub

' ---------------------------------------------------------------------------

sub test_hwNextBackoffSeconds()
    print "== hkNextBackoffSeconds =="
    assertEq("attempt=0",  hkNextBackoffSeconds(0),  2)
    assertEq("attempt=1",  hkNextBackoffSeconds(1),  2)
    assertEq("attempt=2",  hkNextBackoffSeconds(2),  5)
    assertEq("attempt=3",  hkNextBackoffSeconds(3), 10)
    assertEq("attempt=4",  hkNextBackoffSeconds(4), 30)
    assertEq("attempt=99", hkNextBackoffSeconds(99), 30)
end sub

sub test_hwCamIndex()
    print "== hkCamIndex =="
    roster = HK_CAMS()
    assertEq("front",    hkCamIndex("front",    roster), 0)
    assertEq("yard",     hkCamIndex("yard",     roster), 1)
    assertEq("side",     hkCamIndex("side",     roster), 2)
    assertEq("backyard", hkCamIndex("backyard", roster), 3)
    assertEq("missing -> 0",  hkCamIndex("ghost", roster), 0)
end sub

sub test_hwParseInt()
    print "== hkParseInt =="
    assertEq("invalid -> 0", hkParseInt(invalid), 0)
    assertEq("'15' -> 15",   hkParseInt("15"),    15)
    assertEq("'-15' -> -15", hkParseInt("-15"),  -15)
    assertEq("'abc' -> 0",   hkParseInt("abc"),   0)
    assertEq("'' -> 0",      hkParseInt(""),      0)
    assertEq("int 7 -> 7",   hkParseInt(7),       7)
end sub

sub test_hwGridQuadrantPos()
    print "== hkGridQuadrantPos =="
    p0 = hkGridQuadrantPos(0)
    p1 = hkGridQuadrantPos(1)
    p2 = hkGridQuadrantPos(2)
    p3 = hkGridQuadrantPos(3)
    assertEq("0.x", p0[0], 0)   : assertEq("0.y", p0[1], 0)
    assertEq("1.x", p1[0], 960) : assertEq("1.y", p1[1], 0)
    assertEq("2.x", p2[0], 0)   : assertEq("2.y", p2[1], 540)
    assertEq("3.x", p3[0], 960) : assertEq("3.y", p3[1], 540)
end sub

sub test_hwMotionLabel()
    print "== hkMotionLabel =="
    now_ = 100000
    assertEq("ts=0 -> none",       hkMotionLabel(0, now_), "no recent motion")
    assertEq("just now (5s)",      hkMotionLabel(now_ - 5, now_), "motion just now")
    assertEq("5 min ago",          hkMotionLabel(now_ - 300, now_), "motion 5 min ago")
    assertEq("2h ago",             hkMotionLabel(now_ - 7200, now_), "motion 2h ago")
end sub

sub test_hwScrub()
    print "== hkScrub =="
    s1 = hkScrub("foo=1&haToken=secretvalue&bar=2")
    assertContains("haToken redacted", s1, "haToken=*****")
    assertContains("preserves bar", s1, "bar=2")
    s2 = hkScrub("haToken=onlything")
    assertContains("trailing token", s2, "haToken=*****")
    s3 = hkScrub("nothing=here")
    assertEq("no-op when no token", s3, "nothing=here")
end sub

sub test_HW_CAMS_roster()
    print "== HK_CAMS roster =="
    r = HK_CAMS()
    assertEq("count = 4", r.count(), 4)
    assertEq("[0]=front", r[0], "front")
    assertEq("[3]=backyard", r[3], "backyard")
end sub

sub test_HW_CAM_DISPLAY_NAME()
    print "== HK_CAM_DISPLAY_NAME =="
    assertEq("front",    HK_CAM_DISPLAY_NAME("front"),    "Front Door")
    assertEq("yard",     HK_CAM_DISPLAY_NAME("yard"),     "Yard")
    assertEq("backyard", HK_CAM_DISPLAY_NAME("backyard"), "Backyard")
    assertEq("mosaic",   HK_CAM_DISPLAY_NAME("mosaic"),   "Grid")
    assertEq("unknown -> echo", HK_CAM_DISPLAY_NAME("foo"), "foo")
end sub

sub test_substituteAll()
    print "== substituteAll =="
    assertEq("simple",   substituteAll("a b c", " ", "_"),  "a_b_c")
    assertEq("noop",     substituteAll("abc",   "x", "y"),  "abc")
    assertEq("multi",    substituteAll("aaa",   "a", "bb"), "bbbbbb")
    assertEq("empty find", substituteAll("abc", "",  "_"),  "abc")
end sub

sub test_hwOverlayDurationMs()
    print "== hkOverlayDurationMs =="
    assertEq("pip default",     hkOverlayDurationMs("pip",     {}), 30000)
    assertEq("door default",    hkOverlayDurationMs("door",    {}), 6000)
    assertEq("weather default", hkOverlayDurationMs("weather", {}), 10000)
    assertEq("sensor default",  hkOverlayDurationMs("sensor",  {}), 8000)
    assertEq("text default",    hkOverlayDurationMs("text",    {}), 4000)
    assertEq("unknown -> text", hkOverlayDurationMs("ghost",   {}), 4000)
    assertEq("dwell wins",      hkOverlayDurationMs("weather", { dwell: "12" }),    12000)
    assertEq("duration wins",   hkOverlayDurationMs("pip",     { duration: "60" }), 60000)
    assertEq("dwell=0 ignored", hkOverlayDurationMs("door",    { dwell: "0" }),     6000)
end sub

sub test_hwSeverityColor()
    print "== hkSeverityColor =="
    assertEq("high -> live",   hkSeverityColor("high"),   HK_LIVE())
    assertEq("live alias",     hkSeverityColor("live"),   HK_LIVE())
    assertEq("low -> ok",      hkSeverityColor("low"),    HK_OK())
    assertEq("ok alias",       hkSeverityColor("ok"),     HK_OK())
    assertEq("normal -> warn", hkSeverityColor("normal"), HK_WARN())
    assertEq("unset -> warn",  hkSeverityColor(""),       HK_WARN())
end sub

sub test_hkTileRect()
    print "== hkTileRect =="
    grid = { cellW: 600, cellH: 440, gap: 24, originX: 60, originY: 160 }
    r0 = hkTileRect(0, 0, 1, 1, grid)
    assertEq("tile0 x", r0.x, 60)
    assertEq("tile0 y", r0.y, 160)
    assertEq("tile0 w", r0.w, 600)
    assertEq("tile0 h", r0.h, 440)
    r = hkTileRect(2, 1, 1, 1, grid)
    assertEq("col2 x", r.x, 1308)   ' 60 + 2*(600+24)
    assertEq("row1 y", r.y, 624)    ' 160 + 1*(440+24)
    r2 = hkTileRect(2, 0, 1, 2, grid)
    assertEq("span2 h", r2.h, 904)  ' 2*440 + 24
    rd = hkTileRect(0, 0, 1, 1, {})
    assertEq("default w", rd.w, 600)
end sub


sub test_hkModuleKind()
    print "== hkModuleKind =="
    assertEq("weather tile",  hkModuleKind("weather").tileType,  "value")
    assertEq("cameras drill", hkModuleKind("cameras").drill,     "camera")
    assertEq("calendar tile", hkModuleKind("calendar").tileType, "agenda")
    assertEq("timeline tile", hkModuleKind("timeline").tileType, "agenda")
    assertEq("timeline drill", hkModuleKind("timeline").drill, "agenda")
    assertEq("unknown -> value tile", hkModuleKind("ghost").tileType, "value")
    assertEq("laundry tile", hkModuleKind("laundry").tileType, "value")
end sub



sub test_hkBgNextIndex()
    print "== hkBgNextIndex =="
    assertEq("0 of 5 -> 1", hkBgNextIndex(0, 5), 1)
    assertEq("4 of 5 wrap", hkBgNextIndex(4, 5), 0)
    assertEq("single stays", hkBgNextIndex(0, 1), 0)
    assertEq("empty -> 0",   hkBgNextIndex(3, 0), 0)
end sub

sub test_hkBgRotateMs()
    print "== hkBgRotateMs =="
    assertEq("explicit",     hkBgRotateMs({ background: { intervalMs: 9000 } }), 9000)
    assertEq("missing block",hkBgRotateMs({}), 20000)
    assertEq("invalid cfg",  hkBgRotateMs(invalid), 20000)
    assertEq("floored",      hkBgRotateMs({ background: { intervalMs: 100 } }), 5000)
    assertEq("zero -> deflt",hkBgRotateMs({ background: { intervalMs: 0 } }), 20000)
end sub

sub test_hkAgeLabel()
    print "== hkAgeLabel =="
    now_ = 1000000
    assertEq("ts=0 -> never", hkAgeLabel(now_, 0), "never")
    assertEq("just now",      hkAgeLabel(now_, now_ - 2), "just now")
    assertEq("seconds",       hkAgeLabel(now_, now_ - 30), "30s ago")
    assertEq("minutes",       hkAgeLabel(now_, now_ - 300), "5 min ago")
    assertEq("hours",         hkAgeLabel(now_, now_ - 7200), "2h ago")
    assertEq("days",          hkAgeLabel(now_, now_ - 172800), "2d ago")
    assertEq("future clamps", hkAgeLabel(now_, now_ + 50), "just now")
end sub

sub test_hkUptimeLabel()
    print "== hkUptimeLabel =="
    assertEq("zero -> dash", hkUptimeLabel(0), "—")
    assertEq("minutes",      hkUptimeLabel(720000), "12m")           ' 12 min
    assertEq("hours+min",    hkUptimeLabel(11520000), "3h 12m")      ' 3h12m
    assertEq("days+hours",   hkUptimeLabel(90061000), "1d 1h")       ' 1d 1h 1m -> 1d 1h
end sub

' --- glass home --------------------------------------------------------------

sub assertFrame(label as string, got as object, want as object)
    ' Brightnesses compared at 2 dp (BrightScript floats print with noise).
    g = []
    w = []
    for each v in got
        g.push(Int(v * 100 + 0.5).toStr())
    end for
    for each v in want
        w.push(Int(v * 100 + 0.5).toStr())
    end for
    assertEq(label, g.join(","), w.join(","))
end sub

sub test_hkTileRect_roku()
    print "== hkTileRect (layouts.roku 6x4) =="
    grid = { cols: 6, rows: 4, cellW: 289, cellH: 220, originX: 52, originY: 116, gap: 16 }
    assertEq("col5 x", hkTileRect(5, 0, 1, 1, grid).x, 1577)
    assertEq("row3 y", hkTileRect(0, 3, 1, 1, grid).y, 824)
    cam = hkTileRect(4, 0, 2, 2, grid)
    assertEq("2x2 w", cam.w, 594)
    assertEq("2x2 h", cam.h, 456)
    assertEq("2x1 h", hkTileRect(0, 0, 2, 1, grid).h, 220)
    last = hkTileRect(4, 2, 2, 2, grid)
    assertEq("right edge", last.x + last.w, 1866)
    assertEq("bottom edge", last.y + last.h, 1044)
end sub

sub test_hkFreshness()
    print "== hkFreshness =="
    now_ = 1000000
    assertEq("never fetched", hkFreshness(0, now_), "offline")
    assertEq("fresh",         hkFreshness(now_ - 5, now_), "live")
    assertEq("30s is live",   hkFreshness(now_ - 30, now_), "live")
    assertEq("31s lagging",   hkFreshness(now_ - 31, now_), "lagging")
    assertEq("120s lagging",  hkFreshness(now_ - 120, now_), "lagging")
    assertEq("121s offline",  hkFreshness(now_ - 121, now_), "offline")
    assertEq("offline shown needs a fetch", hkOfflineShown("offline", false), false)
    assertEq("offline shown",  hkOfflineShown("offline", true), true)
    assertEq("lagging not offline", hkOfflineShown("lagging", true), false)
end sub

sub test_hkHeaderStatus()
    print "== hkHeaderStatus =="
    s = hkHeaderStatus("offline", false, [])
    assertEq("connecting", s.label, "connecting")
    assertEq("connecting dot", s.dot, HK_OFFLINE())
    assertEq("connecting beats live", hkHeaderStatus("live", false, ["Water"]).label, "connecting")
    assertEq("offline", hkHeaderStatus("offline", true, ["Water"]).label, "offline")
    s = hkHeaderStatus("lagging", true, ["Water"])
    assertEq("lagging", s.label, "lagging")
    assertEq("lagging dot", s.dot, HK_AMBER())
    s = hkHeaderStatus("live", true, ["Water"])
    assertEq("degraded one", s.label, "degraded · Water")
    assertEq("degraded dot", s.dot, HK_AMBER())
    assertEq("degraded two", hkHeaderStatus("live", true, ["Water", "Gas"]).label, "degraded · Water, Gas")
    assertEq("degraded counts", hkHeaderStatus("live", true, ["a", "b", "c"]).label, "degraded · 3")
    s = hkHeaderStatus("live", true, [])
    assertEq("live", s.label, "live")
    assertEq("live dot", s.dot, HK_SAGE())
end sub

sub test_hkClockAndDateLabels()
    print "== hkClockLabel / hkDateLabel =="
    assertEq("evening", hkClockLabel(21, 17), "9:17 PM")
    assertEq("midnight", hkClockLabel(0, 5), "12:05 AM")
    assertEq("noon", hkClockLabel(12, 0), "12:00 PM")
    assertEq("morning", hkClockLabel(9, 59), "9:59 AM")
    assertEq("date", hkDateLabel("Wednesday", 10, 7), "Wednesday, October 7")
    assertEq("bad month", hkDateLabel("Monday", 13, 1), "Monday")
end sub

sub test_hkBurnIn()
    print "== hkBurnIn =="
    slot = 600
    base = 1791400200   ' a slot boundary (divisible by 600)
    seen = {}
    prev = invalid
    for i = 0 to 7
        o = hkBurnIn(base + i * slot)
        assertEq("within 2px " + i.toStr(), (Abs(o[0]) <= 2 and Abs(o[1]) <= 2), true)
        seen[o[0].toStr() + "," + o[1].toStr()] = true
        if prev <> invalid then assertEq("one 2px step " + i.toStr(), Abs(o[0] - prev[0]) + Abs(o[1] - prev[1]), 2)
        prev = o
    end for
    assertEq("8 distinct", seen.count(), 8)
    assertEq("same slot", hkBurnIn(base).join(","), hkBurnIn(base + slot - 1).join(","))
    assertEq("repeats", hkBurnIn(base).join(","), hkBurnIn(base + 8 * slot).join(","))
end sub

sub test_hkGlyphFor()
    print "== hkGlyphFor =="
    assertEq("shipped", hkGlyphFor("fire", "gas"), "fire")
    assertEq("unknown -> kind default", hkGlyphFor("rocket", "water"), "water-outline")
    assertEq("blank -> kind default", hkGlyphFor("", "timeline"), "history")
    assertEq("cameras", hkGlyphFor("", "cameras"), "cctv")
    assertEq("no default", hkGlyphFor("", "ghost"), "")
    assertEq("invalid glyph", hkGlyphFor(invalid, "doors"), "door")
end sub

sub test_hkAccents()
    print "== hkAccentFor / hkItemAccent =="
    assertEq("door open amber", hkAccentFor("door-open"), HK_AMBER())
    assertEq("water", hkAccentFor("water"), HK_WATER())
    assertEq("fire heat", hkAccentFor("fire"), HK_HEAT())
    assertEq("snowflake cool", hkAccentFor("snowflake"), HK_COOL())
    assertEq("washer", hkAccentFor("washing-machine"), HK_WASHER())
    assertEq("dryer", hkAccentFor("tumble-dryer"), HK_DRYER())
    assertEq("else sage", hkAccentFor("flash"), HK_SAGE())
    assertEq("item unlocked", hkItemAccent("lock-open-variant"), HK_AMBER())
    assertEq("item home", hkItemAccent("home-account"), HK_SAGE())
    assertEq("item else muted", hkItemAccent("motion-sensor"), HK_INK_MUTED())
end sub

sub test_hkHexToRoku()
    print "== hkHexToRoku =="
    assertEq("#rrggbb", hkHexToRoku("#00AAFF", "x"), "0x00AAFFFF")
    assertEq("lower", hkHexToRoku("#ff6900", "x"), "0xFF6900FF")
    assertEq("#aarrggbb", hkHexToRoku("#80112233", "x"), "0x11223380")
    assertEq("roku passthrough", hkHexToRoku("0x5B8C7FFF", "x"), "0x5B8C7FFF")
    assertEq("garbage", hkHexToRoku("#GGHHII", "fb"), "fb")
    assertEq("blank", hkHexToRoku("", "fb"), "fb")
    assertEq("invalid", hkHexToRoku(invalid, "fb"), "fb")
end sub

sub test_hkCardKind()
    print "== hkCardKind =="
    assertEq("doors", hkCardKind({ kind: "doors", tile: { type: "value" } }, { doors: [{ id: "front" }] }), "doors")
    assertEq("no doors -> value", hkCardKind({ kind: "doors", tile: { type: "value" } }, { doors: [] }), "value")
    assertEq("doors without array", hkCardKind({ kind: "doors", tile: { type: "value" } }, { tile: {} }), "value")
    assertEq("laundry", hkCardKind({ kind: "laundry", tile: { type: "value" } }, { machines: [{ id: "washer" }] }), "laundry")
    assertEq("laundry no values", hkCardKind({ kind: "laundry", tile: { type: "value" } }, invalid), "value")
    assertEq("agenda", hkCardKind({ kind: "timeline", tile: { type: "agenda" } }, invalid), "agenda")
    assertEq("camera", hkCardKind({ kind: "cameras", tile: { type: "camera" } }, invalid), "camera")
    assertEq("forecast", hkCardKind({ kind: "weather", tile: { type: "forecast" } }, invalid), "forecast")
    assertEq("chart -> value", hkCardKind({ kind: "weather", tile: { type: "chart" } }, invalid), "value")
    assertEq("no tile", hkCardKind({ kind: "gas" }, invalid), "value")
end sub

sub test_hkTileStale()
    print "== hkTileStale =="
    assertEq("no values", hkTileStale(invalid), true)
    assertEq("no tile", hkTileStale({}), true)
    assertEq("blank hero", hkTileStale({ tile: { hero: " " } }), true)
    assertEq("error", hkTileStale({ error: "boom", tile: { hero: "1" } }), true)
    assertEq("flagged", hkTileStale({ stale: true, tile: { hero: "1" } }), true)
    assertEq("string true is not stale", hkTileStale({ stale: "true", tile: { hero: "1" } }), false)
    assertEq("fine", hkTileStale({ stale: false, tile: { hero: "21°" } }), false)
    assertEq("agenda stale", hkAgendaStale({ stale: true }), true)
    assertEq("agenda fine", hkAgendaStale({ items: [] }), false)
end sub

sub test_hkDoorsShown()
    print "== hkDoorsShown =="
    doors = [{ id: "front", state: "closed" }, { id: "garage", state: "open" }, { id: "back", state: "unknown" }]
    assertEq("open/unknown first", idsOf(hkDoorsShown(doors, 2)), "garage,back")
    assertEq("max three", idsOf(hkDoorsShown(doors, 5)), "garage,back,front")
    closed = [{ id: "front", state: "closed" }, { id: "back", state: "closed" }, { id: "side", state: "closed" }, { id: "x", state: "closed" }]
    assertEq("stable order", idsOf(hkDoorsShown(closed, 2)), "front,back")
    assertEq("caps at 3", idsOf(hkDoorsShown(closed, 9)), "front,back,side")
    assertEq("no room", hkDoorsShown(doors, 0).count(), 0)
end sub

function idsOf(list as object) as string
    ids = []
    for each d in list
        ids.push(d.id)
    end for
    return ids.join(",")
end function

sub test_hkLedFrame()
    print "== hkLedFrame =="
    assertFrame("idle", hkLedFrame("idle", 0, 0, false), [0.25, 0, 0, 0])
    assertFrame("idle later", hkLedFrame("idle", 0, 12345, false), [0.25, 0, 0, 0])
    assertFrame("running 3", hkLedFrame("running", 3, 0, false), [1, 1, 1, 0])
    assertFrame("running clamps", hkLedFrame("running", 9, 0, false), [1, 1, 1, 1])
    assertFrame("running negative", hkLedFrame("running", -1, 0, false), [0, 0, 0, 0])
    assertFrame("overtime peak", hkLedFrame("overtime", 0, 625, false), [1, 0, 0, 0])
    assertFrame("overtime trough", hkLedFrame("overtime", 0, 1875, false), [0.15, 0, 0, 0])
    lit = []
    for i = 0 to 6
        f = hkLedFrame("done", 0, i * 120, false)
        for j = 0 to 3
            if f[j] = 1 then lit.push(j.toStr())
        end for
    end for
    assertEq("done ping-pong", lit.join(","), "0,1,2,3,2,1,0")
    assertFrame("calm t0", hkLedFrame("done_calm", 0, 0, false), [0.6, 0, 0, 0])
    assertFrame("calm head+trail", hkLedFrame("done_calm", 0, 450, false), [0.2, 0.6, 0, 0])
    assertFrame("calm turn", hkLedFrame("done_calm", 0, 4 * 450, false), [0, 0, 0.6, 0.2])
    assertFrame("calm wrap", hkLedFrame("done_calm", 0, 6 * 450, false), [0.6, 0.2, 0, 0])
    assertFrame("stale t0", hkLedFrame("idle", 0, 0, true), [1, 0, 0.1, 0.35])
    assertFrame("stale 150", hkLedFrame("idle", 0, 150, true), [0.35, 1, 0, 0.1])
    assertFrame("stale 450", hkLedFrame("idle", 0, 450, true), [0, 0.1, 0.35, 1])
    assertFrame("stale beats running", hkLedFrame("running", 3, 150, true), [0.35, 1, 0, 0.1])
    assertFrame("unknown dark", hkLedFrame("spinning", 4, 0, false), [0, 0, 0, 0])
end sub

sub test_hkLedStepAndColor()
    print "== hkLedStepMs / hkLedAnimates / hkLedColor =="
    assertEq("idle static", hkLedStepMs("idle"), 0)
    assertEq("running static", hkLedStepMs("running"), 0)
    assertEq("overtime", hkLedStepMs("overtime"), 100)
    assertEq("done", hkLedStepMs("done"), 120)
    assertEq("done_calm", hkLedStepMs("done_calm"), 450)
    assertEq("stale", hkLedStepMs("stale"), 150)
    assertEq("animates done", hkLedAnimates("done", false, false), true)
    assertEq("quiet holds", hkLedAnimates("done", false, true), false)
    assertEq("stale machine sweeps", hkLedAnimates("running", true, false), true)
    assertEq("running holds", hkLedAnimates("running", false, false), false)
    assertEq("stale violet", hkLedColor("running", true, "0x00AAFFFF"), HK_LED_STALE())
    assertEq("idle red", hkLedColor("idle", false, "0x00AAFFFF"), HK_LED_IDLE())
    assertEq("machine colour", hkLedColor("done", false, "0x00AAFFFF"), "0x00AAFFFF")
end sub

sub test_hkVisibleRowCount()
    print "== hkVisibleRowCount =="
    act = []
    for i = 1 to 12
        act.push({ kind: "event", title: i.toStr() })
    end for
    rowH = HK_ROW_ACTIVITY()
    assertEq("activity whole rows", hkVisibleRowCount(act, true, 9 * rowH), 9)
    assertEq("activity just short", hkVisibleRowCount(act, true, 9 * rowH - 1), 8)
    assertEq("activity none", hkVisibleRowCount(act, true, rowH - 1), 0)
    assertEq("activity fewer items", hkVisibleRowCount([act[0], act[1]], true, 9 * rowH), 2)
    cal = [{ kind: "header", title: "TODAY" }, { kind: "event", title: "a" }, { kind: "header", title: "TOMORROW" }, { kind: "event", title: "b" }, { kind: "event", title: "c" }]
    assertEq("calendar mixed", hkVisibleRowCount(cal, false, 2 * HK_ROW_DAY() + 3 * HK_ROW_EVENT()), 5)
    assertEq("never ends on a header", hkVisibleRowCount(cal, false, 2 * HK_ROW_DAY() + HK_ROW_EVENT() + 1), 2)
    assertEq("lone header", hkVisibleRowCount([cal[0]], false, 500), 0)
    assertEq("empty", hkVisibleRowCount([], false, 500), 0)
    assertEq("no room", hkVisibleRowCount(cal, false, -5), 0)
end sub

sub test_hkDayLabel()
    print "== hkDayLabel =="
    assertEq("today", hkDayLabel("TODAY"), "Today")
    assertEq("dated", hkDayLabel("WED · OCT 7"), "Wed · Oct 7")
    assertEq("empty", hkDayLabel(""), "")
end sub

sub test_hkWithLayout()
    print "== hkWithLayout =="
    assertEq("plain", hkWithLayout("http://h:1986/api/config", "roku"), "http://h:1986/api/config?layout=roku")
    assertEq("has query", hkWithLayout("http://h/api/card/x.png?w=1", "roku"), "http://h/api/card/x.png?w=1&layout=roku")
    assertEq("no layout", hkWithLayout("http://h/api/state", ""), "http://h/api/state")
end sub

sub test_hkSlimConfig()
    print "== hkSlimConfig =="
    cfg = { grid: { cols: 6 }, modules: [{ id: "water", kind: "water", entities: { flow: "x" }, drill: { type: "value" }, refreshMs: 30000, tile: { type: "value" } }] }
    slim = hkSlimConfig(cfg)
    md = slim.modules[0]
    assertEq("keeps id", md.id, "water")
    assertEq("keeps tile", md.tile.type, "value")
    assertEq("drops entities", md.entities, invalid)
    assertEq("drops drill", md.drill, invalid)
    assertEq("drops refreshMs", md.refreshMs, invalid)
    assertEq("keeps grid", slim.grid.cols, 6)
    assertEq("source untouched", cfg.modules[0].entities.flow, "x")
end sub

sub test_hkStreamUrl()
    print "== hkStreamUrl =="
    streams = { front: { hls: "http://h/front.m3u8" }, mosaic: { hls: "http://h/mosaic.m3u8" }, side: {} }
    assertEq("own stream", hkStreamUrl(streams, "front"), "http://h/front.m3u8")
    assertEq("missing -> mosaic", hkStreamUrl(streams, "yard"), "http://h/mosaic.m3u8")
    assertEq("no hls -> mosaic", hkStreamUrl(streams, "side"), "http://h/mosaic.m3u8")
    assertEq("no mosaic", hkStreamUrl({ front: {} }, "front"), "")
    assertEq("no streams", hkStreamUrl(invalid, "front"), "")
end sub

sub test_hkVideoFit()
    print "== hkVideoFit =="
    sq = hkVideoFit(554, 360)
    assertEq("2x2 body w", sq.w, 554)
    assertEq("2x2 body h", sq.h, 311)
    assertEq("2x2 body x", sq.x, 0)
    assertEq("2x2 body y", sq.y, 24)
    wide = hkVideoFit(400, 90)
    assertEq("letterbox h", wide.h, 90)
    assertEq("pillarbox w", wide.w, 160)
    assertEq("pillarbox x", wide.x, 120)
end sub

sub test_hkDoorLayout()
    print "== hkDoorLayout =="
    two = hkDoorLayout(554, 124)
    assertEq("2x1 cols", two.cols, 2)
    assertEq("2x1 rows", two.rows, 1)
    old = hkDoorLayout(246, 188)
    assertEq("0.11 1x1 cols", old.cols, 1)
    assertEq("0.11 1x1 rows", old.rows, 2)
    assertEq("short 1x1 rows", hkDoorLayout(249, 124).rows, 1)
    assertEq("no room", hkDoorLayout(249, 40).rows, 0)
end sub

sub test_hkTileCam()
    print "== hkTileCam =="
    assertEq("cam", hkTileCam({ type: "camera", cam: "front" }), "front")
    assertEq("thumbCam", hkTileCam({ type: "camera", thumbCam: "yard" }), "yard")
    assertEq("neither", hkTileCam({ type: "camera" }), "mosaic")
    assertEq("no tile", hkTileCam(invalid), "mosaic")
end sub

sub test_hkBgListUpdate()
    print "== hkBgListUpdate =="
    abc = ["a", "b", "c"]
    r = hkBgListUpdate([], abc, "")
    assertEq("first list", r.action, "first")
    assertEq("first idx", r.idx, 0)
    assertEq("failed refresh keeps", hkBgListUpdate(abc, [], "b").action, "keep")
    assertEq("never had one", hkBgListUpdate([], [], "").action, "empty")
    assertEq("same list", hkBgListUpdate(abc, ["a", "b", "c"], "b").action, "same")
    r = hkBgListUpdate(abc, ["a", "b", "x", "c"], "c")
    assertEq("added: swap", r.action, "swap")
    assertEq("added: follows shown", r.idx, 3)
    r = hkBgListUpdate(abc, ["a", "c"], "b")
    assertEq("shown removed: swap", r.action, "swap")
    assertEq("shown removed: next is the first", r.idx, 1)
end sub
