' ModuleTile — one home-page card. See ModuleTile.xml.

sub init()
    m.ring     = m.top.findNode("ring")
    m.card     = m.top.findNode("card")
    m.titleChip = m.top.findNode("titleChip")
    m.stripe   = m.top.findNode("stripe")
    m.title    = m.top.findNode("title")
    m.icon     = m.top.findNode("icon")
    m.hero     = m.top.findNode("hero")
    m.sub      = m.top.findNode("sub")
    m.detail   = m.top.findNode("detail")
    m.agenda   = m.top.findNode("agenda")
    m.rollTimer = m.top.findNode("rollTimer")
    m.thumb    = m.top.findNode("thumb")
    m.camScrim = m.top.findNode("camScrim")
    m.camLabel = m.top.findNode("camLabel")
    m.img      = m.top.findNode("img")
    m.ttype    = ""

    ' Rolling-agenda state. Rows are built once here (render thread; safe) and
    ' shown/positioned by layout(); paintAgenda() fills them, onRoll() advances.
    m.rollOffset = 0
    m.rollSrc = invalid
    m.visibleRows = 4
    m.agRows = []
    for i = 0 to 4
        row = createObject("roSGNode", "Group")
        dot = row.createChild("Rectangle")
        dot.color = HK_BRAND()
        tm = row.createChild("Label")
        tm.color = HK_TEXT_LIGHT_MUTED()
        tm.font = "font:MediumSystemFont"
        mn = row.createChild("Label")
        mn.color = HK_TEXT_CREAM()
        mn.font = "font:MediumBoldSystemFont"
        mn.maxLines = 1
        row.visible = false
        m.agenda.appendChild(row)
        m.agRows.push({ row: row, dot: dot, time: tm, main: mn })
    end for
    m.rollTimer.observeField("fire", "onRoll")
    m.icon.observeField("loadStatus", "onIconLoad")
end sub

' Only reveal the icon once its Poster has actually decoded — never flash a
' broken/stale image while a fetch is in flight or fails.
sub onIconLoad()
    m.icon.visible = (m.icon.loadStatus = "ready")
end sub

sub onDescriptor()
    d = m.top.descriptor
    if d = invalid then return
    m.rollTimer.control = "stop"   ' tile reuse: never carry a stale roll
    m.rollSrc = invalid
    m.ttype = tileTypeOf(d)
    if d.title <> invalid then m.title.text = UCase(d.title.toStr())
    applyVisibility(m.ttype)
    layout()
    onValues()  ' paint whatever values we already hold
end sub

function tileTypeOf(d as object) as string
    t = ""
    if d.tile <> invalid and d.tile.type <> invalid then t = d.tile.type
    if t = "" and d.kind <> invalid then t = hkModuleKind(d.kind).tileType
    if t = "" then t = "value"
    return t
end function

sub applyVisibility(ttype as string)
    isVal = (ttype = "value")
    isAgenda = (ttype = "agenda")
    isCam = (ttype = "camera")
    isImg = (ttype = "chart" or ttype = "image")
    ' hero/sub/detail serve `value` tiles and double as the agenda fallback
    ' (toggled in paintAgenda when no items have arrived yet).
    m.hero.visible = isVal
    m.sub.visible = isVal
    m.detail.visible = isVal
    m.agenda.visible = isAgenda
    m.thumb.visible = isCam
    m.camScrim.visible = isCam
    m.camLabel.visible = isCam
    m.img.visible = isImg
    if not isVal then
        m.icon.visible = false
        m.icon.uri = ""
    end if
end sub

sub layout()
    w = m.top.tileW
    h = m.top.tileH
    m.ring.translation = [-4, -4] : m.ring.width = w + 8 : m.ring.height = h + 8
    m.card.width = w : m.card.height = h
    m.titleChip.translation = [0, 14] : m.titleChip.width = w : m.titleChip.height = 50
    m.stripe.width = w : m.stripe.height = 6
    m.title.translation = [28, 22] : m.title.width = w - 56
    m.hero.translation = [24, 70] : m.hero.width = w - 48
    ' Icon sits in the body beside the hero value, in the gap between the
    ' titleChip (ends y=64) and sub — not the top bar. sub is nudged down
    ' from its old y=178 to clear the larger icon.
    iconPx = HK_TILE_ICON_DISPLAY_PX()
    m.icon.translation = [w - iconPx - 28, 64] : m.icon.width = iconPx : m.icon.height = iconPx
    m.sub.translation = [28, 214] : m.sub.width = w - 56
    m.detail.translation = [28, h - 92] : m.detail.width = w - 56
    m.thumb.translation = [0, 0] : m.thumb.width = w : m.thumb.height = h
    m.camScrim.translation = [0, h - 64] : m.camScrim.width = w : m.camScrim.height = 64
    m.camLabel.translation = [24, h - 52] : m.camLabel.width = w - 48
    m.img.translation = [16, 48] : m.img.width = w - 32 : m.img.height = h - 68

    ' Agenda rows: a left dot, a fixed-width time column, then the main line.
    top = 82
    rowH = 60
    avail = h - top - 12
    vis = avail \ rowH
    if vis < 2 then vis = 2
    if vis > m.agRows.count() then vis = m.agRows.count()
    m.visibleRows = vis
    for i = 0 to m.agRows.count() - 1
        r = m.agRows[i]
        r.row.translation = [24, top + i * rowH]
        r.dot.translation = [0, 12] : r.dot.width = 12 : r.dot.height = 12
        r.time.translation = [22, 0] : r.time.width = 92
        r.main.translation = [120, 0] : r.main.width = w - 24 - 120 - 12
    end for
end sub

sub onValues()
    d = m.top.descriptor
    if d = invalid or m.ttype = "" then return

    if m.ttype = "agenda" then
        paintAgenda()
    else if m.ttype = "value" then
        paintValue()
    else if m.ttype = "camera" then
        paintCamera()
    else if m.ttype = "chart" or m.ttype = "image" then
        paintCard()
    end if
end sub

' --- value tile (also the agenda no-items fallback) ------------------------
sub paintValue()
    tile = invalid
    if m.top.values <> invalid then tile = m.top.values.tile
    if tile <> invalid then
        m.hero.text = strOr(tile.hero, "—")
        m.sub.text = strOr(tile.sub, "")
        m.detail.text = strOr(tile.detail, "")
        m.stripe.color = hkSeverityColor(strOr(tile.severity, "normal"))
    else
        m.hero.text = "—"
        m.sub.text = ""
        m.detail.text = ""
    end if
    paintIcon(m.top.descriptor, tile)
end sub

' Accent icon (weather condition / energy battery / water bucket), placed
' beside the hero value in layout() — sidecar-rendered, see /api/icon/<id>.png.
' `descriptor.icon` (a leftover
' free-form config string) just gates whether this module WANTS an icon at
' all; the actual bucket/condition token that picks the image is
' `tile.icon`, which only changes when the rendered PNG would actually look
' different (see hkHubIconUrl) so an unmoved value never triggers a refetch.
sub paintIcon(d as object, tile as dynamic)
    wantIcon = (d <> invalid and d.icon <> invalid and d.icon.toStr() <> "")
    bucket = ""
    if tile <> invalid and tile.icon <> invalid then bucket = tile.icon.toStr()
    if wantIcon and bucket <> "" and m.top.hubBase <> "" and d.id <> invalid then
        px = HK_TILE_ICON_PX()
        m.icon.uri = hkHubIconUrl(m.top.hubBase, d.id.toStr(), bucket, px, px)
    else
        m.icon.visible = false
        m.icon.uri = ""
    end if
end sub

' --- agenda tile -----------------------------------------------------------
sub paintAgenda()
    d = m.top.descriptor
    items = itemsOf(m.top.values)

    ' Severity stripe follows the most-recent/next event.
    ev = hkAgendaEventRows(items)
    if ev.count() > 0 then
        m.stripe.color = hkSeverityColor(strOr(ev[0].severity, "normal"))
    end if

    if items.count() = 0 then
        ' No items yet — fall back to the value-style hero/sub/detail so the
        ' tile still reads (matches every other card on a cold/empty poll).
        showAgenda(false)
        paintValue()
        return
    end if
    showAgenda(true)

    rotate = false
    if d.tile <> invalid and d.tile.rotate <> invalid then rotate = d.tile.rotate

    if rotate and ev.count() > m.visibleRows then
        ' Rolling ticker over the event rows (drop day headers while cycling).
        ' Only reset position/restart the timer the FIRST time we enter rolling
        ' (m.rollSrc was invalid) — a routine data refresh (every refreshMs) must
        ' not snap the ticker back to the top mid-cycle, or it never gets past
        ' the newest few rows before the next poll yanks it back.
        wasRolling = (m.rollSrc <> invalid)
        m.rollSrc = ev
        if not wasRolling then
            m.rollOffset = 0
            m.rollTimer.duration = hkTileRotateMs(d.tile) / 1000
            m.rollTimer.control = "start"
        end if
        renderWindow(hkAgendaWindow(m.rollSrc, m.rollOffset, m.visibleRows))
    else
        ' Static: show the head of the full list (headers give TODAY/TOMORROW
        ' context on the calendar tile); tile.dropHeaders opts a card like
        ' Recent Activity out of that, so all visible rows are real events.
        m.rollTimer.control = "stop"
        m.rollSrc = invalid
        dropHeaders = false
        if d.tile <> invalid and d.tile.dropHeaders <> invalid then dropHeaders = d.tile.dropHeaders
        renderWindow(hkAgendaWindow(hkAgendaStaticSource(items, ev, dropHeaders), 0, m.visibleRows))
    end if
end sub

sub onRoll()
    if m.rollSrc = invalid then return
    n = m.rollSrc.count()
    if n = 0 then return
    m.rollOffset = (m.rollOffset + 1) mod n
    renderWindow(hkAgendaWindow(m.rollSrc, m.rollOffset, m.visibleRows))
end sub

sub showAgenda(on as boolean)
    m.agenda.visible = on
    m.hero.visible = (not on)
    m.sub.visible = (not on)
    m.detail.visible = (not on)
end sub

sub renderWindow(win as object)
    for i = 0 to m.agRows.count() - 1
        r = m.agRows[i]
        if i < win.count() then
            applyRow(r, win[i])
            r.row.visible = true
        else
            r.row.visible = false
        end if
    end for
end sub

sub applyRow(r as object, it as object)
    kind = strOr(it.kind, "event")
    if kind = "header" then
        r.time.text = ""
        r.main.text = UCase(strOr(it.title, ""))
        r.main.color = HK_BRAND()
        r.main.font = "font:SmallBoldSystemFont"
        r.dot.visible = false
    else
        r.time.text = strOr(it.time, "")
        line = strOr(it.title, "")
        sb = strOr(it.sub, "")
        if sb <> "" then line = line + "  " + sb
        r.main.text = line
        r.main.color = HK_TEXT_CREAM()
        r.main.font = "font:MediumBoldSystemFont"
        r.dot.visible = true
        col = strOr(it.dot, "")
        if col = "" then col = hkSeverityColor(strOr(it.severity, "normal"))
        r.dot.color = col
    end if
end sub

' --- camera tile -----------------------------------------------------------
sub paintCamera()
    d = m.top.descriptor
    cam = ""
    if d.tile <> invalid and d.tile.thumbCam <> invalid then cam = d.tile.thumbCam.toStr()
    m.camLabel.text = UCase(HK_CAM_DISPLAY_NAME(cam))
    base = m.top.snapBase
    if base = "" then base = HK_OVERLAY_SNAPSHOT_BASE()
    if cam <> "" then
        m.thumb.uri = base + "/api/frame.jpeg?src=" + cam + "&t=" + m.top.cacheBust
    end if
end sub

' --- chart / image tile ----------------------------------------------------
sub paintCard()
    d = m.top.descriptor
    card = ""
    if d.tile <> invalid and d.tile.card <> invalid then card = d.tile.card.toStr()
    if card <> "" and m.top.hubBase <> "" then
        m.img.uri = hkHubCardUrl(m.top.hubBase, card, m.top.tileW, m.top.tileH, m.top.cacheBust)
    end if
end sub

sub onFocus()
    f = m.top.focused
    m.ring.visible = f
    if f then
        m.card.color = HK_GLASS_CARD_FOCUS()   ' brighten the glass
    else
        m.card.color = HK_GLASS_CARD()
    end if
end sub

' Items array from a values payload, or [] (never invalid — keeps the non-short-
' circuiting `or` guards from dereferencing invalid).
function itemsOf(values as object) as object
    if values = invalid then return []
    it = values.items
    if it = invalid then return []
    return it
end function

function strOr(v as dynamic, dflt as string) as string
    if v = invalid then return dflt
    return v.toStr()
end function
