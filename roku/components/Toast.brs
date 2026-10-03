' Toast — slide-in / hold / slide-out top-centre notification.

sub init()
    m.bg = m.top.findNode("toastBg")
    m.border = m.top.findNode("toastBorder")
    m.label = m.top.findNode("toastLabel")
    m.slideIn = m.top.findNode("slideIn")
    m.slideOut = m.top.findNode("slideOut")
    m.holdTimer = m.top.findNode("holdTimer")

    m.holdTimer.observeField("fire", "onHoldElapsed")
    m.slideOut.observeField("state", "onSlideOutDone")

    m.queue = []
    m.showing = false
end sub

sub onRequest()
    req = m.top.request
    if req = invalid then return
    if req.text = invalid then return
    m.queue.push(req)
    if not m.showing then dequeue()
end sub

sub dequeue()
    if m.queue.count() = 0 then
        m.showing = false
        return
    end if
    m.showing = true
    req = m.queue.shift()

    sev = req.severity
    if sev = invalid then sev = "normal"

    color = "0xD9A441FF"  ' warn / amber
    if sev = "high" then color = "0xD4673EFF"  ' live / coral
    if sev = "low"  then color = "0x6B9080FF"  ' ok / sage
    m.border.color = color

    m.label.text = req.text
    m.bg.visible = true
    m.border.visible = true
    m.label.visible = true
    m.slideIn.control = "start"

    duration = 3
    if req.durationMs <> invalid then duration = (req.durationMs / 1000)
    if sev = "high" and duration < 5 then duration = 5
    m.holdTimer.duration = duration
    m.holdTimer.control = "start"
end sub

sub onHoldElapsed()
    m.slideOut.control = "start"
end sub

sub onSlideOutDone()
    if m.slideOut.state <> "stopped" then return
    m.bg.visible = false
    m.border.visible = false
    m.label.visible = false
    dequeue()
end sub
