' HomeGroup — the HAku home wall. See HomeGroup.xml.

function HEADER_RIGHT() as integer : return 1848 : end function   ' grid right edge less card padding
function HEADER_MID() as integer : return 70 : end function       ' vertical centre of the header band

sub init()
    m.shift = m.top.findNode("shift")
    m.clock = m.top.findNode("clock")
    m.date = m.top.findNode("date")
    m.statusDot = m.top.findNode("statusDot")
    m.status = m.top.findNode("status")
    m.tilesGroup = m.top.findNode("tiles")
    m.banner = m.top.findNode("banner")
    m.bannerFill = m.top.findNode("bannerFill")
    m.bannerText = m.top.findNode("bannerText")
    m.empty = m.top.findNode("empty")
    m.clockTimer = m.top.findNode("clockTimer")
    m.statusTimer = m.top.findNode("statusTimer")

    m.fonts = hkFontSet()
    m.clock.font = m.fonts.clock
    m.date.font = m.fonts.date
    m.status.font = m.fonts.title
    m.bannerText.font = m.fonts.sub
    m.empty.font = m.fonts.sub
    m.bannerFill.blendColor = HK_OFFLINE()

    m.tiles = []
    m.offline = false

    m.clockTimer.observeField("fire", "onClockTick")
    m.statusTimer.observeField("fire", "updateStatus")
    m.statusTimer.control = "start"
    onClockTick()
    updateStatus()
end sub

' ---------------------------------------------------------------------------
' Build the cards from /api/config
' ---------------------------------------------------------------------------
sub onConfig()
    cfg = m.top.config
    if cfg = invalid or cfg.modules = invalid then return

    for each t in m.tiles
        m.tilesGroup.removeChild(t)
    end for
    m.tiles = []

    grid = cfg.grid
    if grid = invalid then grid = {}
    cols = hkNumOr(grid, "cols", 3)

    i = 0
    for each md in cfg.modules
        tdef = md.tile
        if tdef = invalid then tdef = {}
        col = hkNumOr(tdef, "col", i mod cols)
        row = hkNumOr(tdef, "row", i \ cols)
        rect = hkTileRect(col, row, hkNumOr(tdef, "w", 1), hkNumOr(tdef, "h", 1), grid)

        tile = CreateObject("roSGNode", "ModuleTile")
        tile.fonts = m.fonts
        tile.tileW = rect.w
        tile.tileH = rect.h
        tile.translation = [rect.x, rect.y]
        tile.offline = m.offline
        tile.hubBase = m.top.hubBase
        if m.top.streams <> invalid then tile.streams = m.top.streams
        tile.camActive = m.top.camActive
        tile.camOverride = m.top.homeCam
        tile.descriptor = md
        tile.addFields({ moduleId: hkStrOr(md.id, ""), feedKey: feedKeyOf(md) })
        m.tilesGroup.appendChild(tile)
        m.tiles.push(tile)
        i = i + 1
    end for

    m.empty.visible = (m.tiles.count() = 0)
    updateHasCam()
    onState()  ' paint any state we already have
end sub

' ---------------------------------------------------------------------------
' Wall-wide inputs for the bodies: the sidecar base, discovery's streams, and the
' decoder grant MainScene gives the camera card while home is showing
' ---------------------------------------------------------------------------
sub onHubBase()
    for each t in m.tiles
        t.hubBase = m.top.hubBase
    end for
end sub

sub onStreams()
    for each t in m.tiles
        t.streams = m.top.streams
    end for
    updateHasCam()
end sub

sub onCamActive()
    for each t in m.tiles
        t.camActive = m.top.camActive
    end for
end sub

sub onHomeCam()
    for each t in m.tiles
        t.camOverride = m.top.homeCam
    end for
end sub

' hasCam: a camera card whose camera discovery can play (MainScene then hands it the
' decoder instead of the keep-awake clip).
sub updateHasCam()
    has = false
    cfg = m.top.config
    if cfg <> invalid and type(cfg.modules) = "roArray" then
        for each md in cfg.modules
            if md.tile <> invalid and hkStrOr(md.tile.type, "") = "camera" then
                if hkStreamUrl(m.top.streams, hkTileCam(md.tile)) <> "" then has = true
            end if
        end for
    end if
    if has <> m.top.hasCam then m.top.hasCam = has
end sub

function feedKeyOf(md as object) as string
    if md.feedKey <> invalid then return md.feedKey.toStr()
    if md.id <> invalid then return md.id.toStr()
    return ""
end function

' ---------------------------------------------------------------------------
' Push /api/state values into each card
' ---------------------------------------------------------------------------
sub onState()
    s = m.top.state
    if s = invalid then return
    for each t in m.tiles
        fk = t.feedKey
        if fk <> "" and s.doesExist(fk) then t.values = s[fk]
    end for
    updateStatus()
end sub

' ---------------------------------------------------------------------------
' Header status, offline dimming and banner (every poll, and every 5 s, since a
' hung poll never reports back)
' ---------------------------------------------------------------------------
sub updateStatus()
    fresh = hkFreshness(m.top.lastOk, hkNowSeconds())
    offline = hkOfflineShown(fresh, m.top.fetched)
    if offline <> m.offline then
        m.offline = offline
        for each t in m.tiles
            t.offline = offline
        end for
    end if

    degraded = []
    for each t in m.tiles
        if t.stale and t.descriptor <> invalid then degraded.push(hkStrOr(t.descriptor.title, t.moduleId))
    end for
    st = hkHeaderStatus(fresh, m.top.fetched, degraded)
    m.status.text = st.label
    w = hkTextWidth(m.status)
    m.status.translation = [HEADER_RIGHT() - w, HEADER_MID() - 36]
    m.statusDot.translation = [HEADER_RIGHT() - w - 12 - 14, HEADER_MID() - 7]
    hkTint(m.statusDot, st.dot)

    m.banner.visible = offline
    if offline then paintBanner()
end sub

' "No data since 9:41 PM", or "No data yet": a grey pill centred low over the cards.
sub paintBanner()
    text = "No data yet"
    if m.top.lastOk > 0 then
        dt = CreateObject("roDateTime")
        dt.FromSeconds(m.top.lastOk)
        dt.ToLocalTime()
        text = "No data since " + hkClockLabel(dt.GetHours(), dt.GetMinutes())
    end if
    m.bannerText.text = text
    w = hkTextWidth(m.bannerText) + 2 * 26
    h = 56
    m.bannerFill.width = w
    m.bannerFill.height = h
    m.bannerText.translation = [26, 0]
    m.bannerText.height = h
    m.banner.translation = [(1920 - w) \ 2, 1080 - 22 - h]
end sub

' ---------------------------------------------------------------------------
' HA focusModule= takeover: light the card for a moment (no route change)
' ---------------------------------------------------------------------------
sub onAttention()
    id = m.top.attention
    for each t in m.tiles
        if t.moduleId = id then t.attention = true
    end for
end sub

' ---------------------------------------------------------------------------
' Clock, date and the burn-in shift; re-armed at each minute boundary
' ---------------------------------------------------------------------------
sub onClockTick()
    dt = CreateObject("roDateTime")
    now_ = dt.AsSeconds()
    dt.ToLocalTime()
    m.clock.text = hkClockLabel(dt.GetHours(), dt.GetMinutes())
    cw = hkTextWidth(m.clock)
    m.date.text = hkDateLabel(dt.GetWeekday(), dt.GetMonth(), dt.GetDayOfMonth())
    ' Bottom-aligned boxes; nudge the smaller face up so the baselines meet.
    m.date.translation = [72 + cw + 20, 34 - 6]

    off = hkBurnIn(now_)
    m.shift.translation = [off[0], off[1]]

    m.clockTimer.duration = 60 - dt.GetSeconds() + 0.2
    m.clockTimer.control = "start"
end sub
