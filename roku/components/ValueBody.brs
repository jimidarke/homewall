' ValueBody — see ValueBody.xml.

sub init()
    m.hero = m.top.createChild("Label")
    m.sub = m.top.createChild("Label")
    m.detail = m.top.createChild("Label")
    m.bar = m.top.createChild("Rectangle")
    m.bar.visible = false
    for each l in [m.hero, m.sub, m.detail]
        l.vertAlign = "bottom"
    end for
end sub

sub paint()
    f = m.top.fonts
    if f = invalid then return
    bw = m.top.bodyW
    bh = m.top.bodyH
    t = invalid
    v = m.top.values
    if v <> invalid then t = v.tile
    if t <> invalid and type(t) <> "roAssociativeArray" then t = invalid

    hero = "—"
    subText = ""
    detail = ""
    if t <> invalid then
        h = hkStrOr(t.hero, "").trim()
        if h <> "" then hero = h
        subText = hkStrOr(t.sub, "")
        detail = hkStrOr(t.detail, "")
    end if

    ' Fixed slots from the bottom, so neighbouring cards' lines stay level. A short body
    ' (the 0.12 wall's 1x1 is 124 px) takes the tight slots, so the hero clears the title.
    slots = { hero: 76, sub: 40, detail: 32 }
    if bh < 148 then slots = { hero: 64, sub: 32, detail: 28 }
    detailY = bh - slots.detail
    subY = detailY - slots.sub
    heroY = subY - slots.hero
    m.hero.translation = [0, heroY]
    m.hero.height = slots.hero
    hkFitLabel(m.hero, hero, [f.hero, f.hero2, f.hero3], bw)
    m.hero.color = HK_INK()
    if m.top.alert then m.hero.color = HK_CORAL()

    m.sub.font = f.sub
    m.sub.color = HK_INK()
    m.sub.text = subText
    m.sub.translation = [0, subY]
    m.sub.width = bw
    m.sub.height = slots.sub - 2

    m.detail.font = f.detail
    m.detail.color = HK_INK_MUTED()
    m.detail.text = detail
    m.detail.translation = [0, detailY]
    m.detail.width = bw
    m.detail.height = slots.detail

    ' Level bar: on the card's bottom edge, down in its padding; faint ink at rest.
    level = -1
    if t <> invalid and t.level <> invalid then level = hkParseInt(t.level)
    if level >= 0 then
        if level > 100 then level = 100
        m.bar.visible = (level > 0)
        m.bar.translation = [0, bh + 4]
        m.bar.height = 5
        m.bar.width = Int(bw * level / 100)
        if m.top.lit then m.bar.color = m.top.tone else m.bar.color = HK_INK_FAINT()
    else
        m.bar.visible = false
    end if
end sub
