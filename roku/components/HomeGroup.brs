' HomeGroup — the HAku card-grid home page. See HomeGroup.xml.

sub init()
    m.tilesGroup = m.top.findNode("tiles")
    m.clock      = m.top.findNode("clock")
    m.empty      = m.top.findNode("empty")
    m.tiles      = []
    m.tileMeta   = []
    m.cellMap    = {}
    m.cols       = 3
    m.rows       = 2
    m.focusIdx   = 0
    updateClock()
end sub

' ---------------------------------------------------------------------------
' Build the grid from /api/config
' ---------------------------------------------------------------------------
sub onConfig()
    cfg = m.top.config
    if cfg = invalid or cfg.modules = invalid then return

    for each t in m.tiles
        m.tilesGroup.removeChild(t)
    end for
    m.tiles = []
    m.tileMeta = []
    m.cellMap = {}

    grid = cfg.grid
    if grid = invalid then grid = {}
    m.cols = hkNumOr(grid, "cols", 3)
    m.rows = hkNumOr(grid, "rows", 2)

    i = 0
    for each md in cfg.modules
        tdef = md.tile
        if tdef = invalid then tdef = {}
        col = hkNumOr(tdef, "col", i mod m.cols)
        row = hkNumOr(tdef, "row", i \ m.cols)
        wsp = hkNumOr(tdef, "w", 1)
        hsp = hkNumOr(tdef, "h", 1)
        rect = hkTileRect(col, row, wsp, hsp, grid)

        tile = createObject("roSGNode", "ModuleTile")
        tile.tileW = rect.w
        tile.tileH = rect.h
        tile.hubBase = m.top.hubBase
        tile.snapBase = m.top.snapBase
        tile.translation = [rect.x, rect.y]
        tile.descriptor = md
        m.tilesGroup.appendChild(tile)
        m.tiles.push(tile)
        m.tileMeta.push({ col: col, row: row, id: strOrEmpty(md.id), feedKey: feedKeyOf(md) })

        for cc = col to col + wsp - 1
            for rr = row to row + hsp - 1
                m.cellMap[(rr * m.cols + cc).toStr()] = i
            end for
        end for
        i = i + 1
    end for

    m.empty.visible = (m.tiles.count() = 0)
    if m.focusIdx >= m.tiles.count() then m.focusIdx = 0
    applyFocus()
    onState()  ' paint any state we already have
end sub

function feedKeyOf(md as object) as string
    if md.feedKey <> invalid then return md.feedKey.toStr()
    if md.id <> invalid then return md.id.toStr()
    return ""
end function

' ---------------------------------------------------------------------------
' Push /api/state values into each tile
' ---------------------------------------------------------------------------
sub onState()
    s = m.top.state
    if s = invalid then return
    ts = "0"
    if s.ts <> invalid then ts = s.ts.toStr()

    for i = 0 to m.tiles.count() - 1
        fk = m.tileMeta[i].feedKey
        m.tiles[i].cacheBust = ts
        if fk <> "" and s.doesExist(fk) then
            m.tiles[i].values = s[fk]
        end if
    end for
    updateClock()
end sub

' ---------------------------------------------------------------------------
' Focus / navigation
' ---------------------------------------------------------------------------
function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if m.tiles.count() = 0 then return false

    if key = "OK" then
        meta = m.tileMeta[m.focusIdx]
        if meta.id <> "" then
            m.top.selectedModule = meta.id
            hkEvent("module_open", { id: meta.id })
        end if
        return true
    else if key = "left" or key = "right" or key = "up" or key = "down" then
        moveFocus(key)
        return true
    end if
    return false
end function

sub moveFocus(key as string)
    meta = m.tileMeta[m.focusIdx]
    idx = meta.row * m.cols + meta.col
    guard = 0
    while guard < (m.cols + m.rows + 2)
        guard = guard + 1
        n = hkGridNeighbor(idx, key, m.cols, m.rows)
        if n = idx then return  ' at the grid edge — no move
        idx = n
        k = idx.toStr()
        if m.cellMap.doesExist(k) then
            tIdx = m.cellMap[k]
            if tIdx <> m.focusIdx then
                m.focusIdx = tIdx
                applyFocus()
                hkEvent("tile_focus", { idx: tIdx, id: m.tileMeta[tIdx].id })
                return
            end if
        end if
    end while
end sub

sub applyFocus()
    for i = 0 to m.tiles.count() - 1
        m.tiles[i].focused = (i = m.focusIdx)
    end for
end sub

' Called by MainScene when HomeGroup (re)gains focus, to re-assert the ring.
sub onShow()
    applyFocus()
    updateClock()
end sub

' ---------------------------------------------------------------------------
' Clock
' ---------------------------------------------------------------------------
sub updateClock()
    dt = createObject("roDateTime")
    dt.toLocalTime()
    h = dt.getHours()
    mm = dt.getMinutes()
    ampm = "AM"
    if h >= 12 then ampm = "PM"
    h12 = h mod 12
    if h12 = 0 then h12 = 12
    mmStr = mm.toStr()
    if mm < 10 then mmStr = "0" + mmStr
    m.clock.text = h12.toStr() + ":" + mmStr + " " + ampm
end sub

function strOrEmpty(v as dynamic) as string
    if v = invalid then return ""
    return v.toStr()
end function
