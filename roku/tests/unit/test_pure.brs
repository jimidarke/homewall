' tests/unit/test_pure.brs — pure-logic test suite for HAku.
' Run via: npx brs source/Config.brs tests/unit/test_pure.brs
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
    test_hkGridNeighbor()
    test_hkModuleKind()
    test_hkAgendaHelpers()
    test_hkTileRotateMs()
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

sub test_hkGridNeighbor()
    print "== hkGridNeighbor =="
    ' 3 cols x 2 rows, row-major:  0 1 2 / 3 4 5
    assertEq("0 right -> 1",  hkGridNeighbor(0, "right", 3, 2), 1)
    assertEq("2 right clamp", hkGridNeighbor(2, "right", 3, 2), 2)
    assertEq("0 left clamp",  hkGridNeighbor(0, "left",  3, 2), 0)
    assertEq("1 down -> 4",   hkGridNeighbor(1, "down",  3, 2), 4)
    assertEq("4 up -> 1",     hkGridNeighbor(4, "up",    3, 2), 1)
    assertEq("3 up -> 0",     hkGridNeighbor(3, "up",    3, 2), 0)
    assertEq("5 down clamp",  hkGridNeighbor(5, "down",  3, 2), 5)
end sub

sub test_hkModuleKind()
    print "== hkModuleKind =="
    assertEq("weather tile",  hkModuleKind("weather").tileType,  "value")
    assertEq("cameras drill", hkModuleKind("cameras").drill,     "camera")
    assertEq("calendar tile", hkModuleKind("calendar").tileType, "agenda")
    assertEq("timeline tile", hkModuleKind("timeline").tileType, "agenda")
    assertEq("timeline drill", hkModuleKind("timeline").drill, "agenda")
    assertEq("unknown -> value tile", hkModuleKind("ghost").tileType, "value")
end sub

sub test_hkAgendaHelpers()
    print "== hkAgenda helpers =="
    items = [
        { kind: "header", title: "TODAY" },
        { kind: "event",  title: "A" },
        { kind: "event",  title: "B" },
        { kind: "event",  title: "C" }
    ]
    ev = hkAgendaEventRows(items)
    assertEq("event rows count", ev.count(), 3)
    assertEq("first event",      ev[0].title, "A")
    assertEq("invalid -> empty", hkAgendaEventRows(invalid).count(), 0)

    w = hkAgendaWindow(ev, 0, 2)
    assertEq("win size",  w.count(), 2)
    assertEq("win[0]",    w[0].title, "A")
    assertEq("win[1]",    w[1].title, "B")
    w2 = hkAgendaWindow(ev, 2, 2)          ' wraps past end: C, A
    assertEq("wrap[0]",   w2[0].title, "C")
    assertEq("wrap[1]",   w2[1].title, "A")
    assertEq("size>=count -> all", hkAgendaWindow(ev, 0, 9).count(), 3)
    assertEq("empty items -> 0",   hkAgendaWindow([], 0, 3).count(), 0)
    assertEq("size 0 -> empty",    hkAgendaWindow(ev, 0, 0).count(), 0)

    assertEq("static source: headers by default", hkAgendaStaticSource(items, ev, false)[0].title, "TODAY")
    assertEq("static source: dropHeaders -> events only", hkAgendaStaticSource(items, ev, true)[0].title, "A")
end sub

sub test_hkTileRotateMs()
    print "== hkTileRotateMs =="
    assertEq("default",      hkTileRotateMs({}), 4000)
    assertEq("invalid",      hkTileRotateMs(invalid), 4000)
    assertEq("explicit",     hkTileRotateMs({ rotateMs: 6000 }), 6000)
    assertEq("floored",      hkTileRotateMs({ rotateMs: 100 }), 1500)
    assertEq("zero -> deflt", hkTileRotateMs({ rotateMs: 0 }), 4000)
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
