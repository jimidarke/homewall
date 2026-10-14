' GridGroup — 2x2 mosaic + focus ring + per-quadrant motion dots.
'
' One Video node plays the server-side `mosaic` stream (xstack on nserver
' is already doing the 4-up). Four invisible focusable hit zones map to
' quadrants. D-pad moves the focus ring; OK selects.

' Quadrant order matches HK_CAMS(): [front, yard, side, backyard]
'   0 = TL (front)   1 = TR (yard)
'   2 = BL (side)    3 = BR (backyard)

sub init()
    m.player    = m.top.findNode("player")
    m.focusRing = m.top.findNode("focusRing")
    m.ringAnim  = m.top.findNode("ringAnim")
    m.ringMover = m.top.findNode("ringMover")

    m.dots = {
        front:    m.top.findNode("dotTL")
        yard:     m.top.findNode("dotTR")
        side:     m.top.findNode("dotBL")
        backyard: m.top.findNode("dotBR")
    }

    m.focusIdx = 0
    m.player.observeField("state", "onPlayerStateChanged")
    m.lastMotionByCam = {}
    placeRing()
end sub

sub onActiveChanged()
    if m.top.active then startMosaic() else stopMosaic()
end sub

sub onStreamsChanged()
    if m.top.active then startMosaic()
end sub

sub onMotionChanged()
    motion = m.top.motion
    if motion = invalid then return
    for each cam in motion
        m.lastMotionByCam[cam] = motion[cam]
    end for
    refreshDots()
end sub

sub refreshDots()
    now_ = hkNowSeconds()
    for each cam in m.dots
        ts = m.lastMotionByCam[cam]
        if ts <> invalid and (now_ - hkParseInt(ts)) < 300 then
            m.dots[cam].color = HK_LIVE()
        else
            m.dots[cam].color = HK_OK()
        end if
    end for
end sub

sub startMosaic()
    streams = m.top.streams
    if streams = invalid or streams.mosaic = invalid or streams.mosaic.hls = invalid then
        hkLog("GridGroup: no mosaic URL yet")
        return
    end if
    url = streams.mosaic.hls
    hkLog("GridGroup startMosaic url=" + url)

    content = createObject("roSGNode", "ContentNode")
    content.url = url
    content.streamFormat = "hls"
    content.live = true
    m.player.mute = true
    m.player.content = content
    m.player.control = "play"
    placeRing()
end sub

sub stopMosaic()
    m.player.control = "stop"
end sub

sub onPlayerStateChanged()
    hkDebug("grid player state=" + m.player.state)
end sub

sub placeRing()
    target = hkGridQuadrantPos(m.focusIdx)
    cur = m.focusRing.translation
    m.ringMover.keyValue = [ [cur[0], cur[1]], [target[0], target[1]] ]
    m.ringAnim.control = "start"
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if not m.top.active then return false

    if key = "left" then
        if m.focusIdx = 1 then m.focusIdx = 0
        if m.focusIdx = 3 then m.focusIdx = 2
        placeRing()
        return true
    else if key = "right" then
        if m.focusIdx = 0 then m.focusIdx = 1
        if m.focusIdx = 2 then m.focusIdx = 3
        placeRing()
        return true
    else if key = "up" then
        if m.focusIdx = 2 then m.focusIdx = 0
        if m.focusIdx = 3 then m.focusIdx = 1
        placeRing()
        return true
    else if key = "down" then
        if m.focusIdx = 0 then m.focusIdx = 2
        if m.focusIdx = 1 then m.focusIdx = 3
        placeRing()
        return true
    else if key = "OK" then
        roster = HK_CAMS()
        m.top.selectedCam = roster[m.focusIdx]
        return true
    else if key = "back" then
        m.top.cancel = true
        return true
    end if
    return false
end function
