' DiagScreen — `*` diagnostic / status page. See DiagScreen.xml.
' Renders three sections as aligned key/value label columns. Back or `*` closes.

sub init()
    m.devKeys  = m.top.findNode("devKeys")
    m.devVals  = m.top.findNode("devVals")
    m.discKeys = m.top.findNode("discKeys")
    m.discVals = m.top.findNode("discVals")
    m.haKeys   = m.top.findNode("haKeys")
    m.haVals   = m.top.findNode("haVals")
end sub

sub onDevice()
    d = m.top.device
    if d = invalid then return
    keys = ["Name", "Model", "Roku OS", "IP", "Network", "Memory", "Uptime"]
    vals = [so(d.friendly), so(d.model), so(d.os), so(d.ip), so(d.network), so(d.memory), so(d.uptime)]
    m.devKeys.text = keys.join(Chr(10))
    m.devVals.text = vals.join(Chr(10))
end sub

sub onDiscovery()
    d = m.top.discovery
    if d = invalid then return
    keys = ["Sidecar", "Host", "Schema", "Streams"]
    vals = [so(d.sidecar), so(d.host), so(d.schema), so(d.streams)]
    m.discKeys.text = keys.join(Chr(10))
    m.discVals.text = vals.join(Chr(10))
end sub

sub onHealth()
    h = m.top.health
    if h = invalid then
        m.haKeys.text = "Sidecar"
        m.haVals.text = "…"
        return
    end if

    keys = []
    vals = []

    reach = "unreachable"
    if h.reachable = true then reach = "reachable"
    keys.push("Sidecar") : vals.push(reach)

    ha = h.ha
    if ha <> invalid then
        conn = "disconnected"
        if ha.connected = true then conn = "connected"
        keys.push("HA") : vals.push(conn)
        keys.push("HA URL") : vals.push(so(ha.url))
        tok = "absent"
        if ha.token_present = true then tok = "present"
        keys.push("Token") : vals.push(tok)
        age = "never"
        if ha.last_ok_ts <> invalid then age = hkAgeLabel(hkNowSeconds(), hkParseInt(ha.last_ok_ts))
        keys.push("Last poll") : vals.push(age)
        if ha.entity_count <> invalid then
            keys.push("Entities") : vals.push(ha.entity_count.toStr())
        end if
        if ha.last_error <> invalid then
            keys.push("Error") : vals.push(ha.last_error.toStr())
        end if
    else
        keys.push("HA") : vals.push("—")
    end if

    m.haKeys.text = keys.join(Chr(10))
    m.haVals.text = vals.join(Chr(10))
end sub

' Back bubbles to MainScene (-> goHome); `*` sets dismiss; everything else is
' consumed so keys don't leak to the background while the screen is up.
function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "back" then return false
    if key = "options" then
        m.top.dismiss = true
        return true
    end if
    return true
end function

function so(v as dynamic) as string
    if v = invalid then return "—"
    s = v.toStr()
    if s = "" then return "—"
    return s
end function
