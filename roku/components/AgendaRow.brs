' AgendaRow — one MarkupList row for the agenda drill. See AgendaRow.xml.

sub init()
    m.rowbg   = m.top.findNode("rowbg")
    m.hdrline = m.top.findNode("hdrline")
    m.dot     = m.top.findNode("dot")
    m.time    = m.top.findNode("time")
    m.title   = m.top.findNode("title")
    m.sub     = m.top.findNode("sub")
end sub

' Position everything once the list hands us a size. Event rows are single-line:
' [dot] [time col] [title …] [sub, right]. Header rows: a rule + an uppercase label.
sub onSize()
    w = m.top.width
    h = m.top.height
    if w <= 0 or h <= 0 then return
    m.rowbg.width = w : m.rowbg.height = h
    m.dot.translation = [10, (h - 14) / 2] : m.dot.width = 14 : m.dot.height = 14
    m.time.translation = [40, (h - 34) / 2] : m.time.width = 150
    m.title.translation = [206, (h - 40) / 2] : m.title.width = w - 206 - 300
    m.sub.translation = [w - 296, (h - 34) / 2] : m.sub.width = 280
    m.hdrline.translation = [40, h - 3] : m.hdrline.width = w - 80 : m.hdrline.height = 2
    renderContent()
end sub

sub onContent()
    renderContent()
end sub

sub renderContent()
    c = m.top.itemContent
    if c = invalid then return
    if c.rowKind = "header" then
        m.title.text = UCase(c.rowTitle)
        m.title.color = HK_BRAND()
        m.title.font = "font:MediumBoldSystemFont"
        m.title.translation = [40, (m.top.height - 30) / 2]
        m.time.text = ""
        m.sub.text = ""
        m.dot.visible = false
        m.hdrline.visible = true
        m.rowbg.visible = false
    else
        m.time.text = c.rowTime
        m.title.text = c.rowTitle
        m.title.color = HK_TEXT_CREAM()
        m.title.font = "font:LargeBoldSystemFont"
        m.title.translation = [206, (m.top.height - 40) / 2]
        m.sub.text = c.rowSub
        m.dot.visible = true
        col = c.rowDot
        if col = "" then col = hkSeverityColor(c.rowSeverity)
        m.dot.color = col
        m.hdrline.visible = false
        m.rowbg.visible = true
    end if
end sub

' MarkupList sets focusPercent (0..1) on the focused row — draw our own subtle
' glass highlight instead of the default focus bitmap (drawFocusFeedback=false).
sub onFocusPercent()
    c = m.top.itemContent
    isHeader = (c <> invalid and c.rowKind = "header")
    if m.top.focusPercent > 0.5 and not isHeader then
        m.rowbg.color = HK_GLASS_CARD_FOCUS()
    else
        m.rowbg.color = "0x00000000"
    end if
end sub
