' Hud — lower-third widget. Re-renders on field change. Visibility driven by
' visibleHud field; LiveGroup auto-hides via its own timer.

sub init()
    m.camNameLabel = m.top.findNode("camName")
    m.motionLabel  = m.top.findNode("motionLabelNode")
    m.connDot      = m.top.findNode("connDot")
    m.latencyLabel = m.top.findNode("latencyLabel")
    m.dotPager     = m.top.findNode("dotPager")
    m.slideIn      = m.top.findNode("slideIn")
    m.slideOut     = m.top.findNode("slideOut")
end sub

sub onRender()
    m.camNameLabel.text = UCase(HK_CAM_DISPLAY_NAME(m.top.cam))
    m.motionLabel.text = m.top.motionLabel
    m.latencyLabel.text = m.top.latencyText

    if m.top.connected = "live" then
        m.connDot.color = HK_LIVE()
    else if m.top.connected = "warn" then
        m.connDot.color = HK_WARN()
    else
        m.connDot.color = HK_OK()
    end if

    renderDotPager()
end sub

sub renderDotPager()
    ' Strip current children and rebuild — count is small (4) so cheap.
    while m.dotPager.getChildCount() > 0
        m.dotPager.removeChild(m.dotPager.getChild(0))
    end while

    rosterStr = m.top.cams
    if rosterStr = "" then return
    roster = rosterStr.split(",")
    activeCam = m.top.cam
    spacing = 22
    for i = 0 to roster.count() - 1
        dot = createObject("roSGNode", "Rectangle")
        dot.width = 10
        dot.height = 10
        dot.translation = [i * spacing, 0]
        if roster[i] = activeCam then
            dot.color = HK_BRAND()
        else
            dot.color = HK_TEXT_MUTED()
        end if
        m.dotPager.appendChild(dot)
    end for
end sub

sub onVisibleChanged()
    if m.top.visibleHud then
        m.slideOut.control = "stop"
        m.slideIn.control = "start"
    else
        m.slideIn.control = "stop"
        m.slideOut.control = "start"
    end if
end sub
