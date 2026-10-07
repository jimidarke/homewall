' DoorsBody — see DoorsBody.xml.

function COL_GAP() as integer : return 20 : end function

sub init()
    m.rows = []
end sub

function makeRow() as object
    g = m.top.createChild("Group")
    r = { group: g }
    r.glyph = hkPoster(g, "", 40, 40)
    r.label = g.createChild("Label")
    r.state = g.createChild("Label")
    r.age = g.createChild("Label")
    r.label.vertAlign = "bottom"
    r.state.vertAlign = "bottom"
    r.age.vertAlign = "top"
    m.rows.push(r)
    return r
end function

sub paint()
    f = m.top.fonts
    v = m.top.values
    if f = invalid or v = invalid or type(v.doors) <> "roArray" then return
    lay = hkDoorLayout(m.top.bodyW, m.top.bodyH)
    colW = m.top.bodyW
    if lay.cols = 2 then colW = (m.top.bodyW - COL_GAP()) \ 2
    shown = hkDoorsShown(v.doors, lay.cols * lay.rows)
    while m.rows.count() < shown.count()
        makeRow()
    end while
    for i = 0 to m.rows.count() - 1
        r = m.rows[i]
        r.group.visible = (i < shown.count())
        if i < shown.count() then
            ' Across, then down: in a 2-wide card the first two doors sit side by side.
            x = (i mod lay.cols) * (colW + COL_GAP())
            y = (i \ lay.cols) * (HK_DOOR_ROW() + HK_DOOR_GAP())
            paintRow(r, shown[i], f, colW, x, y)
        end if
    end for
end sub

sub paintRow(r as object, door as object, f as object, bw as integer, x as integer, y as integer)
    st = hkStrOr(door.state, "")
    if st = "open" then
        word = "Open"
        color = HK_AMBER()
        if door.severity = "high" then color = HK_CORAL()
    else if st = "closed" then
        word = "Closed"
        color = HK_INK()
    else
        word = "Unknown"
        color = HK_OFFLINE()
    end if
    r.group.translation = [x, y]

    r.glyph.uri = hkGlyphUri(hkGlyphFor(door.glyph, "doors"), 40)
    r.glyph.translation = [0, 12]
    ' A closed door's glyph stays as muted as a resting chip.
    if st = "closed" then hkTint(r.glyph, HK_INK_MUTED()) else hkTint(r.glyph, color)

    r.state.font = f.state
    r.state.color = color
    r.state.text = word
    sw = hkTextWidth(r.state)
    r.state.translation = [bw - sw, -4]
    r.state.height = 42

    r.age.font = f.detail
    r.age.color = HK_INK_MUTED()
    r.age.text = hkStrOr(door.age, "")
    aw = hkTextWidth(r.age)
    r.age.translation = [bw - aw, 38]
    r.age.height = 28

    r.label.font = f.sub
    r.label.color = HK_INK()
    r.label.text = hkStrOr(door.label, "")
    r.label.translation = [54, 0]
    r.label.height = 36
    r.label.width = bw - 54 - sw - 10
end sub
