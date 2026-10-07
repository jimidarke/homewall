' ModuleTile — one glass card. See ModuleTile.xml.

' Card geometry (px): the tablet's 14 dp padding and 48 dp header row at TV scale.
function TILE_PAD() as integer : return 20 : end function
function TILE_HEADER() as integer : return 60 : end function     ' title row = the chip's height
function TILE_BODY_Y() as integer : return 84 : end function     ' body top, under the header row
function TILE_PAD_BOTTOM() as integer : return 12 : end function

sub init()
    m.fill = m.top.findNode("fill")
    m.glow = m.top.findNode("glow")
    m.content = m.top.findNode("content")
    m.title = m.top.findNode("title")
    m.chip = m.top.findNode("chip")
    m.glyph = m.top.findNode("glyph")
    m.body = m.top.findNode("body")
    m.rim = m.top.findNode("rim")
    m.edge = m.top.findNode("edge")
    m.fade = m.top.findNode("fade")
    m.rimFade = m.top.findNode("rimFade")
    m.glowFade = m.top.findNode("glowFade")
    m.chipFade = m.top.findNode("chipFade")
    m.attentionTimer = m.top.findNode("attentionTimer")
    m.attentionTimer.observeField("fire", "onAttentionEnd")

    m.kind = ""
    m.bodyNode = invalid
    m.isStale = true
    m.attn = false
    m.accent = HK_SAGE()        ' held: a fading card keeps the accent it lit up in
    m.target = { rim: 0.0, glow: 0.0, chip: 0.0 }

    m.fill.blendColor = HK_NIGHT()
    m.fill.opacity = HK_GLASS_FILL_OPACITY()
end sub

sub onDescriptor()
    d = m.top.descriptor
    if d = invalid then return
    layout()
    m.title.text = hkStrOr(d.title, "")
    m.kind = ""                 ' a new descriptor rebuilds its body
    onValues()
end sub

sub layout()
    w = m.top.tileW
    h = m.top.tileH
    pad = TILE_PAD()
    for each p in [m.fill, m.glow, m.rim, m.edge]
        p.width = w
        p.height = h
    end for
    f = m.top.fonts
    if f <> invalid then m.title.font = f.title
    m.title.color = HK_INK_MUTED()
    m.title.translation = [pad, pad]
    m.title.width = w - 2 * pad - 60 - 12
    m.title.height = TILE_HEADER()
    m.title.vertAlign = "center"
    m.chip.translation = [w - pad - 60, pad]
    m.glyph.translation = [w - pad - 50, pad + 10]
    m.body.translation = [pad, TILE_BODY_Y()]
end sub

sub onValues()
    d = m.top.descriptor
    if d = invalid then return
    v = m.top.values
    kind = hkCardKind(d, v)
    if kind <> m.kind then buildBody(kind)

    if kind = "agenda" then
        m.isStale = hkAgendaStale(v)
    else if kind = "camera" then
        m.isStale = false       ' the feed shows its own offline state
    else
        m.isStale = hkTileStale(v)
    end if
    m.top.stale = m.isStale
    applyState()
    if m.bodyNode <> invalid and v <> invalid then m.bodyNode.values = v
end sub

sub buildBody(kind as string)
    if m.bodyNode <> invalid then m.body.removeChild(m.bodyNode)
    m.bodyNode = invalid
    m.kind = kind
    comps = { value: "ValueBody", doors: "DoorsBody", laundry: "LaundryBody", agenda: "AgendaBody", forecast: "ForecastBody", camera: "CameraBody" }
    if not comps.doesExist(kind) then return
    b = CreateObject("roSGNode", comps[kind])
    b.fonts = m.top.fonts
    b.descriptor = m.top.descriptor
    b.bodyW = m.top.tileW - 2 * TILE_PAD()
    b.bodyH = m.top.tileH - TILE_BODY_Y() - TILE_PAD_BOTTOM()
    m.body.appendChild(b)
    m.bodyNode = b
    passDown()
end sub

' The wall-wide inputs a body may take: the sidecar base (the forecast chart), and
' discovery's streams and the decoder grant (the camera feed).
sub passDown()
    b = m.bodyNode
    if b = invalid then return
    if b.hasField("hubBase") then b.hubBase = m.top.hubBase
    if b.hasField("streams") and m.top.streams <> invalid then b.streams = m.top.streams
    if b.hasField("active") then b.active = m.top.camActive
end sub

' Colour the card for its current state (tablet GlassCard + CardTone).
sub applyState()
    d = m.top.descriptor
    if d = invalid then return
    tile = invalid
    v = m.top.values
    if v <> invalid and type(v) = "roAssociativeArray" then tile = v.tile
    if tile <> invalid and type(tile) <> "roAssociativeArray" then tile = invalid

    glyphName = ""
    if tile <> invalid then glyphName = hkGlyphFor(tile.glyph, d.kind) else glyphName = hkGlyphFor(invalid, d.kind)
    quiet = m.isStale or m.top.offline
    ' Agenda, camera and forecast cards take no active or alert styling.
    styled = (m.kind = "value" or m.kind = "doors" or m.kind = "laundry")
    active = false
    alert = false
    if styled and tile <> invalid and not quiet then
        active = (tile.active = true)
        alert = (tile.severity = "high")
    end if
    if m.attn and not m.top.offline then active = true
    if active then m.accent = hkAccentFor(glyphName)
    lit = active or alert
    tone = m.accent
    if alert then tone = HK_CORAL()

    m.glyph.uri = hkGlyphUri(glyphName, 40)
    if lit then hkTint(m.glyph, tone) else hkTint(m.glyph, HK_INK_MUTED())
    rgb = Left(tone, 8) + "FF"
    m.chip.blendColor = rgb
    m.rim.blendColor = rgb
    m.glow.blendColor = rgb

    target = { rim: 0.0, glow: 0.0, chip: 0.0 }
    if lit then
        target.rim = HK_LIT_RIM_OPACITY()
        if alert then target.rim = 1.0
        target.glow = HK_GLOW_OPACITY()
        target.chip = HK_CHIP_LIT_OPACITY()
    end if
    fadeTo(target, lit)

    fade = 1.0
    if m.isStale then fade = HK_STALE_OPACITY()
    if m.top.offline and HK_OFFLINE_OPACITY() < fade then fade = HK_OFFLINE_OPACITY()
    m.content.opacity = fade

    if m.bodyNode <> invalid then
        m.bodyNode.quiet = quiet
        m.bodyNode.lit = lit
        m.bodyNode.alert = alert
        m.bodyNode.tone = tone
    end if
end sub

' 600 ms in, 1,200 ms out (tablet ACTIVATE_MS / DEACTIVATE_MS).
sub fadeTo(target as object, lit as boolean)
    if target.rim = m.target.rim and target.glow = m.target.glow and target.chip = m.target.chip then return
    m.target = target
    m.fade.control = "stop"
    m.rimFade.keyValue = [m.rim.opacity, target.rim]
    m.glowFade.keyValue = [m.glow.opacity, target.glow]
    m.chipFade.keyValue = [m.chip.opacity, target.chip]
    if lit then m.fade.duration = 0.6 else m.fade.duration = 1.2
    m.fade.control = "start"
end sub

' An HA focusModule= takeover points at this card: lit in its accent for a few seconds.
sub onAttention()
    if not m.top.attention then return
    m.attn = true
    m.attentionTimer.control = "stop"
    m.attentionTimer.control = "start"
    applyState()
end sub

sub onAttentionEnd()
    m.attn = false
    applyState()
end sub
