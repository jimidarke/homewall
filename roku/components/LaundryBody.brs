' LaundryBody — see LaundryBody.xml.

function LINE_H() as integer : return 36 : end function
function BAR_Y() as integer : return 46 : end function      ' line + 10
function BAR_H() as integer : return 14 : end function
function MACHINE_H() as integer : return 60 : end function
' Compact machine for a short card (the 0.12 wall's 1x1 body is 124 px): the bar sits
' 6 px under the line and thins to 10 px, so two stacked machines fit in 120 px.
function BAR_Y_COMPACT() as integer : return 42 : end function
function BAR_H_COMPACT() as integer : return 10 : end function
function MACHINE_H_COMPACT() as integer : return 52 : end function
function MACHINE_GAP() as integer : return 16 : end function
function SEG_GAP() as integer : return 8 : end function
function LABEL_MAX() as integer : return 132 : end function
function SIDE_BY_SIDE() as integer : return 540 : end function
function LED_UNLIT() as float : return 0.08 : end function

sub init()
    m.slots = []
end sub

function makeSlot(i as integer) as object
    g = m.top.createChild("Group")
    s = { group: g, t: 0, mode: "", leds: 0, stale: false, color: HK_SAGE() }
    s.glyph = hkPoster(g, "", 32, 32)
    s.label = g.createChild("Label")
    s.status = g.createChild("Label")
    s.label.vertAlign = "center"
    s.status.vertAlign = "center"
    s.segs = []
    for k = 0 to 3
        s.segs.push(hkPoster(g, "pkg:/images/glass/seg.9.png", 10, BAR_H()))
    end for
    s.timer = g.createChild("Timer")
    s.timer.id = "led" + i.toStr()
    s.timer.repeat = true
    s.timer.observeField("fire", "onLedStep")
    m.slots.push(s)
    return s
end function

sub paint()
    f = m.top.fonts
    v = m.top.values
    if f = invalid or v = invalid or type(v.machines) <> "roArray" then return
    bw = m.top.bodyW
    perRow = 1
    if bw >= SIDE_BY_SIDE() then perRow = 2
    colW = bw
    if perRow = 2 then colW = (bw - 20) \ 2
    n = v.machines.count()
    machineH = MACHINE_H()
    m.barY = BAR_Y()
    m.barH = BAR_H()
    if machineRows(m.top.bodyH, MACHINE_H()) * perRow < n then
        machineH = MACHINE_H_COMPACT()
        m.barY = BAR_Y_COMPACT()
        m.barH = BAR_H_COMPACT()
    end if
    fitRows = machineRows(m.top.bodyH, machineH)
    if n > fitRows * perRow then n = fitRows * perRow
    while m.slots.count() < n
        makeSlot(m.slots.count())
    end while
    for i = 0 to m.slots.count() - 1
        s = m.slots[i]
        if i < n then
            s.group.visible = true
            s.group.translation = [(i mod perRow) * (colW + 20), (i \ perRow) * (machineH + MACHINE_GAP())]
            paintMachine(s, v.machines[i], f, colW)
        else
            s.group.visible = false
            s.timer.control = "stop"
        end if
    end for
end sub

' Whole machines of height h that fit a body bh px tall.
function machineRows(bh as integer, h as integer) as integer
    return (bh + MACHINE_GAP()) \ (h + MACHINE_GAP())
end function

sub paintMachine(s as object, mc as object, f as object, colW as integer)
    glyph = hkGlyphFor(mc.glyph, "laundry")
    color = hkHexToRoku(mc.color, hkAccentFor(glyph))
    stale = (mc.stale = true)
    s.glyph.uri = hkGlyphUri(glyph, 32)
    s.glyph.translation = [0, 2]
    if stale then hkTint(s.glyph, HK_OFFLINE()) else hkTint(s.glyph, color)

    s.label.font = f.sub
    s.label.color = HK_INK()
    s.label.text = hkStrOr(mc.label, "")
    s.label.height = LINE_H()
    labelW = hkTextWidth(s.label)
    if labelW > LABEL_MAX() then labelW = LABEL_MAX()
    s.label.width = labelW
    s.label.translation = [40, 0]

    ' The status takes the rest of the line, shrinking before it ellipsizes; if even the
    ' smallest size can't fit, the label gives way (the glyph's colour still names it).
    s.status.color = HK_INK()
    s.status.height = LINE_H()
    statusX = 40 + labelW + 8
    text = hkStrOr(mc.status, "")
    sizes = [f.status, f.status2, f.status3]
    w = hkFitLabel(s.status, text, sizes, colW - statusX)
    s.label.visible = true
    if s.status.width > 0 then          ' hkFitLabel clipped it: nothing fit
        s.label.visible = false
        statusX = 40
        w = hkFitLabel(s.status, text, sizes, colW - statusX)
    end if
    s.status.translation = [colW - w, 0]

    segW = (colW - 3 * SEG_GAP()) \ 4
    for k = 0 to 3
        s.segs[k].translation = [k * (segW + SEG_GAP()), m.barY]
        s.segs[k].width = segW
        s.segs[k].height = m.barH
    end for

    mode = hkStrOr(mc.mode, "")
    leds = hkParseInt(mc.leds)
    changed = (mode <> s.mode or stale <> s.stale)
    s.mode = mode
    s.leds = leds
    s.stale = stale
    s.color = hkLedColor(mode, stale, color)
    if hkLedAnimates(mode, stale, m.top.quiet) then
        if changed or s.timer.control <> "start" then
            s.t = 0
            m_ = mode
            if stale then m_ = "stale"
            s.timer.duration = hkLedStepMs(m_) / 1000.0
            s.timer.control = "start"
        end if
    else
        s.timer.control = "stop"
        s.t = 0
    end if
    drawBar(s)
end sub

sub drawBar(s as object)
    frame = hkLedFrame(s.mode, s.leds, s.t, s.stale)
    for k = 0 to 3
        hkTint(s.segs[k], s.color)
        a = frame[k]
        if a < LED_UNLIT() then a = LED_UNLIT()
        s.segs[k].opacity = a
    end for
end sub

sub onLedStep(event as object)
    id = event.getNode()
    for each s in m.slots
        if s.timer.id = id then
            s.t = s.t + Int(s.timer.duration * 1000 + 0.5)
            drawBar(s)
            return
        end if
    end for
end sub
