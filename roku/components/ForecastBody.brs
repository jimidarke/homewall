' ForecastBody — see ForecastBody.xml.

function FC_DAYS() as integer : return 3 : end function

sub init()
    m.cols = []
    for i = 0 to FC_DAYS() - 1
        g = m.top.createChild("Group")
        c = { group: g }
        c.day = g.createChild("Label")
        c.glyph = hkPoster(g, "", 56, 56)
        c.hi = g.createChild("Label")
        c.lo = g.createChild("Label")
        c.day.horizAlign = "center"
        c.hi.horizAlign = "right"
        c.hi.vertAlign = "bottom"
        c.lo.vertAlign = "bottom"
        m.cols.push(c)
    end for
    m.none = m.top.createChild("Label")
    m.none.text = "No forecast"
    m.none.visible = false
end sub

sub paint()
    f = m.top.fonts
    if f = invalid then return
    bw = m.top.bodyW
    colW = bw \ FC_DAYS()
    y0 = (m.top.bodyH - 140) \ 2
    days = []
    v = m.top.values
    if v <> invalid and type(v.outlook) = "roArray" then days = v.outlook

    m.none.font = f.detail
    m.none.color = HK_INK_MUTED()
    m.none.visible = (days.count() = 0)

    for i = 0 to FC_DAYS() - 1
        c = m.cols[i]
        c.group.visible = (i < days.count())
        if i < days.count() then
            day = days[i]
            c.group.translation = [i * colW, y0]
            c.day.font = f.detail
            c.day.color = HK_INK_MUTED()
            c.day.text = hkStrOr(day.label, "")
            c.day.width = colW
            c.day.height = 30

            c.glyph.uri = hkGlyphUri(hkGlyphFor(day.glyph, "weather"), 56)
            c.glyph.translation = [(colW - 56) \ 2, 36]
            hkTint(c.glyph, HK_INK())

            c.hi.font = f.fcHi
            c.hi.color = HK_INK()
            c.hi.text = hkStrOr(day.hi, "—")
            c.hi.translation = [0, 98]
            c.hi.width = colW \ 2 - 4
            c.hi.height = 42

            c.lo.font = f.detail
            c.lo.color = HK_INK_MUTED()
            c.lo.text = hkStrOr(day.lo, "")
            c.lo.translation = [colW \ 2 + 4, 98]
            c.lo.height = 38
        end if
    end for
end sub
