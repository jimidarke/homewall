' ModuleScreen — generic module drill-down. See ModuleScreen.xml.

sub init()
    m.title = m.top.findNode("title")
    m.hero  = m.top.findNode("hero")
    m.card  = m.top.findNode("card")
    m.agendaList = m.top.findNode("agendaList")
    m.agendaSig = ""
end sub

sub onDescriptor()
    d = m.top.descriptor
    if d = invalid then return
    m.agendaSig = ""   ' new module — force an agenda rebuild (and reset scroll)
    if d.title <> invalid then m.title.text = d.title.toStr()
    render()
end sub

sub onValues()
    render()
end sub

sub render()
    d = m.top.descriptor
    if d = invalid then return

    ' Header summary line (from the module's value-tile projection).
    v = m.top.values
    if v <> invalid and v.tile <> invalid then
        line = strOr(v.tile.hero, "") + "   " + strOr(v.tile.sub, "")
        det = strOr(v.tile.detail, "")
        if det <> "" then line = line + "      " + det
        m.hero.text = line
    end if

    if drillType(d) = "agenda" then
        renderAgenda(v)
    else
        renderCard(d)
    end if
end sub

function drillType(d as object) as string
    if d.drill <> invalid and d.drill.type <> invalid then return d.drill.type.toStr()
    if d.kind <> invalid then return hkModuleKind(d.kind).drill
    return ""
end function

' Full scrollable agenda (timeline / calendar): map the sidecar's items into
' AgendaContent nodes for the MarkupList.
sub renderAgenda(v as object)
    m.card.visible = false
    m.agendaList.visible = true

    items = []
    if v <> invalid and v.items <> invalid then items = v.items

    ' Skip the rebuild when nothing changed so the 10s state poll doesn't yank
    ' the user's scroll position back to the top mid-read.
    sig = agendaSig(items)
    if sig = m.agendaSig then return
    m.agendaSig = sig

    root = createObject("roSGNode", "ContentNode")
    for each it in items
        if it <> invalid then
            c = root.createChild("AgendaContent")
            c.rowKind = strOr(it.kind, "event")
            c.rowTime = strOr(it.time, "")
            c.rowTitle = strOr(it.title, "")
            c.rowSub = strOr(it.sub, "")
            c.rowSeverity = strOr(it.severity, "normal")
            c.rowDot = strOr(it.dot, "")
        end if
    end for
    m.agendaList.content = root
end sub

' Cheap content signature so unchanged polls don't rebuild the list.
function agendaSig(items as object) as string
    s = items.count().toStr()
    for each it in items
        if it <> invalid then
            s = s + "|" + strOr(it.time, "") + strOr(it.title, "") + strOr(it.sub, "")
        end if
    end for
    return s
end function

sub renderCard(d as object)
    m.agendaList.visible = false
    cardPath = ""
    if d.drill <> invalid and d.drill.card <> invalid then cardPath = d.drill.card.toStr()
    if cardPath <> "" and m.top.hubBase <> "" then
        m.card.uri = hkHubCardUrl(m.top.hubBase, cardPath, 1120, 720, m.top.cacheBust)
        m.card.visible = true
    else
        m.card.visible = false
    end if
end sub

' Called by MainScene when this screen is shown, so the right node holds focus:
' the agenda list (for D-pad scroll) or this Group (static card, nothing to scroll).
sub takeFocus()
    if drillType(m.top.descriptor) = "agenda" then
        m.agendaList.setFocus(true)
    else
        m.top.setFocus(true)
    end if
end sub

' Card drills consume nothing — MainScene.onKeyEvent routes Back to home. Agenda
' drills keep focus on the MarkupList (which consumes up/down); Back bubbles here
' (unconsumed) then up to MainScene.
function onKeyEvent(key as string, press as boolean) as boolean
    return false
end function

function strOr(v as dynamic, dflt as string) as string
    if v = invalid then return dflt
    return v.toStr()
end function
