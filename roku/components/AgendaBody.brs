' AgendaBody — see AgendaBody.xml.

sub init()
    m.rows = []
    m.empty = m.top.createChild("Label")
    m.empty.text = "Nothing yet"
    m.empty.visible = false
end sub

function makeRow() as object
    g = m.top.createChild("Group")
    r = { group: g }
    r.mark = hkPoster(g, "", 32, 32)
    r.title = g.createChild("Label")
    r.meta = g.createChild("Label")
    r.time = g.createChild("Label")
    r.title.vertAlign = "center"
    r.meta.vertAlign = "center"
    r.time.vertAlign = "center"
    m.rows.push(r)
    return r
end function

sub paint()
    f = m.top.fonts
    d = m.top.descriptor
    if f = invalid or d = invalid then return
    activity = false
    if d.tile <> invalid and d.tile.dropHeaders = true then activity = true

    items = []
    v = m.top.values
    if v <> invalid and type(v.items) = "roArray" then
        for each it in v.items
            if type(it) = "roAssociativeArray" then
                if it.kind = invalid then it.kind = "event"
                if not (activity and it.kind = "header") then items.push(it)
            end if
        end for
    end if

    m.empty.font = f.detail
    m.empty.color = HK_INK_MUTED()
    m.empty.visible = (items.count() = 0)

    n = hkVisibleRowCount(items, activity, m.top.bodyH)
    while m.rows.count() < n
        makeRow()
    end while
    y = 0
    for i = 0 to m.rows.count() - 1
        r = m.rows[i]
        r.group.visible = (i < n)
        if i < n then
            it = items[i]
            r.group.translation = [0, y]
            if activity then
                paintActivity(r, it, f)
                y = y + HK_ROW_ACTIVITY()
            else if it.kind = "header" then
                paintDay(r, it, f)
                y = y + HK_ROW_DAY()
            else
                paintEvent(r, it, f)
                y = y + HK_ROW_EVENT()
            end if
        end if
    end for
end sub

' One line (the 0.12 wall's 2x2 card): the glyph (or a dot when this build doesn't ship
' it) in the row's accent, the title, then the sub muted in whatever room is left, and
' the time on the right like a calendar event.
sub paintActivity(r as object, it as object, f as object)
    bw = m.top.bodyW
    rowH = HK_ROW_ACTIVITY()
    glyph = hkStrOr(it.glyph, "")
    accent = hkItemAccent(glyph)
    if HK_GLYPHS().doesExist(glyph) then
        r.mark.uri = hkGlyphUri(glyph, 32)
        r.mark.width = 32
        r.mark.height = 32
        r.mark.translation = [0, (rowH - 32) \ 2]
    else
        r.mark.uri = "pkg:/images/glass/dot.png"
        r.mark.width = 14
        r.mark.height = 14
        r.mark.translation = [9, (rowH - 14) \ 2]
    end if
    hkTint(r.mark, accent)
    r.mark.visible = true

    r.time.font = f.detail
    r.time.color = HK_INK_MUTED()
    r.time.text = hkStrOr(it.time, "")
    r.time.height = rowH
    tw = 0
    if r.time.text <> "" then tw = hkTextWidth(r.time)
    r.time.translation = [bw - tw, 0]
    r.time.visible = (tw > 0)
    right = bw - tw
    if tw > 0 then right = right - 12

    r.title.font = f.agendaTitle
    r.title.color = HK_INK()
    r.title.text = hkStrOr(it.title, "")
    r.title.translation = [46, 0]
    r.title.height = rowH
    r.title.vertAlign = "center"
    titleW = hkTextWidth(r.title)
    if titleW > right - 46 then titleW = right - 46
    r.title.width = titleW

    ' The sub only when a useful stretch of it fits; a clipped "· o…" reads as noise.
    sub_ = hkStrOr(it.sub, "").trim()
    metaX = 46 + titleW + 10
    r.meta.visible = (sub_ <> "" and right - metaX >= 60)
    if r.meta.visible then
        r.meta.font = f.detail
        r.meta.color = HK_INK_MUTED()
        r.meta.text = "· " + sub_
        r.meta.translation = [metaX, 0]
        r.meta.width = right - metaX
        r.meta.height = rowH
    end if
end sub

sub paintDay(r as object, it as object, f as object)
    r.mark.visible = false
    r.meta.visible = false
    r.time.visible = false
    r.title.font = f.detail
    r.title.color = HK_SAGE()
    r.title.text = hkDayLabel(hkStrOr(it.title, ""))
    r.title.translation = [0, 0]
    r.title.width = m.top.bodyW
    r.title.height = HK_ROW_DAY()
    r.title.vertAlign = "bottom"
end sub

sub paintEvent(r as object, it as object, f as object)
    bw = m.top.bodyW
    r.mark.uri = "pkg:/images/glass/dot.png"
    r.mark.width = 14
    r.mark.height = 14
    r.mark.translation = [0, 12]
    hkTint(r.mark, hkHexToRoku(it.dot, HK_SAGE()))
    r.mark.visible = true
    r.meta.visible = false

    r.time.font = f.detail
    r.time.color = HK_INK_MUTED()
    r.time.text = hkStrOr(it.time, "")
    r.time.height = HK_ROW_EVENT()
    tw = 0
    if r.time.text <> "" then tw = hkTextWidth(r.time)
    r.time.translation = [bw - tw, 0]
    r.time.visible = (tw > 0)

    r.title.font = f.agendaTitle
    r.title.color = HK_INK()
    r.title.text = hkStrOr(it.title, "")
    r.title.translation = [24, 0]
    r.title.height = HK_ROW_EVENT()
    r.title.vertAlign = "center"
    gap = 0
    if tw > 0 then gap = 12
    r.title.width = bw - 24 - tw - gap
end sub
