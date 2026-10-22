' CameraBody — see CameraBody.xml.

function REST_AFTER() as integer : return 4 : end function     ' errors in a row before resting
function REST_S() as integer : return 300 : end function       ' rest before trying the stream again
function STALL_S() as integer : return 90 : end function       ' not playing this long: restart

sub init()
    m.video = m.top.findNode("video")
    m.offline = m.top.findNode("offline")
    m.offlineGlyph = m.top.findNode("offlineGlyph")
    m.offlineText = m.top.findNode("offlineText")
    m.backoff = m.top.findNode("backoff")
    m.rest = m.top.findNode("rest")
    m.watchdog = m.top.findNode("watchdog")
    m.refresh = m.top.findNode("refresh")
    m.refresh.duration = HK_STREAM_REFRESH_S()

    m.video.observeField("state", "onVideoState")
    m.backoff.observeField("fire", "onBackoff")
    m.rest.observeField("fire", "onRestEnd")
    m.watchdog.observeField("fire", "onWatchdog")
    m.refresh.observeField("fire", "onRefresh")

    ' The keep-awake clip the card plays while it rests (see MainScene's keepAwake).
    m.keepAwake = createObject("roSGNode", "ContentNode")
    m.keepAwake.url = "pkg:/images/keepawake.mp4"
    m.keepAwake.streamFormat = "mp4"

    m.mode = "off"          ' off | cam | rest
    m.url = ""
    m.cam = ""
    m.attempts = 0
    m.lastGood = 0
    m.reported = ""
end sub

' Every input lands here: start, keep or stop the feed for (active, url).
sub sync()
    paintOffline()

    tile = invalid
    if m.top.descriptor <> invalid then tile = m.top.descriptor.tile
    m.cam = hkHomeCam(tile, m.top.camOverride, m.top.streams)
    url = hkStreamUrl(m.top.streams, m.cam)
    if not m.top.active or url = "" then
        stopAll()
        showOffline(m.top.active)      ' active with no stream: nothing to show
        return
    end if
    if url = m.url and m.mode <> "off" then return
    m.url = url
    m.attempts = 0
    startCam()
end sub

sub startCam()
    m.mode = "cam"
    m.rest.control = "stop"
    m.backoff.control = "stop"
    showOffline(false)
    placeVideo("feed")
    content = createObject("roSGNode", "ContentNode")
    content.url = m.url
    content.streamFormat = "hls"
    content.live = true
    m.video.mute = true
    m.video.content = content
    m.video.control = "play"
    m.lastGood = hkNowSeconds()
    m.watchdog.control = "start"
    m.refresh.control = "stop"
    m.refresh.control = "start"
    report("start")
end sub

sub stopAll()
    if m.mode <> "off" then report("stop")
    m.mode = "off"
    m.backoff.control = "stop"
    m.rest.control = "stop"
    m.watchdog.control = "stop"
    m.refresh.control = "stop"
    m.video.control = "stop"
    placeVideo("hidden")
    m.url = ""
end sub

sub onVideoState()
    st = m.video.state
    if m.mode = "cam" then
        if st = "playing" then
            m.attempts = 0
            m.lastGood = hkNowSeconds()
            report("playing")
        else if st = "error" or st = "finished" then
            retry()
        end if
    else if m.mode = "rest" then
        if st = "playing" then report("rest_clip")    ' the screensaver guard is running
        if st = "finished" then restartClip()
    end if
end sub

' Back off on the live view's schedule; after REST_AFTER errors in a row, rest.
sub retry()
    m.attempts = m.attempts + 1
    m.video.control = "stop"
    if m.attempts >= REST_AFTER() then
        startRest()
        return
    end if
    report("retry")
    m.backoff.duration = hkNextBackoffSeconds(m.attempts)
    m.backoff.control = "start"
end sub

sub onBackoff()
    if m.mode = "cam" and m.top.active then startCam()
end sub

' "Camera offline", and the keep-awake clip on this same node so the screensaver stays
' away while the one decoder is still ours.
sub startRest()
    m.mode = "rest"
    m.refresh.control = "stop"     ' the rest ends in a fresh startCam anyway
    report("rest")
    showOffline(true)
    placeVideo("clip")
    m.video.content = m.keepAwake
    m.video.control = "play"
    m.rest.duration = REST_S()
    m.rest.control = "start"
end sub

sub onRestEnd()
    if m.mode <> "rest" or not m.top.active then return
    m.attempts = 0
    startCam()
end sub

' Roku OS drops a stream 4 h after it started with no remote input: start it afresh.
sub onRefresh()
    if m.mode <> "cam" or not m.top.active then return
    report("refresh")
    m.video.control = "stop"
    startCam()
end sub

sub restartClip()
    m.video.control = "stop"
    m.video.control = "play"
end sub

' A feed that stopped playing without an error (a stalled buffer), or a resting clip
' whose loop dropped: start it again.
sub onWatchdog()
    st = m.video.state
    moving = (st = "playing" or st = "buffering" or st = "prebuffering")
    if m.mode = "cam" then
        if st = "playing" then
            m.lastGood = hkNowSeconds()
        else if hkNowSeconds() - m.lastGood > STALL_S() then
            report("stall")
            startCam()
        end if
    else if m.mode = "rest" and not moving then
        restartClip()
    end if
end sub

' The Video node punches a black hole in the glass wherever it sits, playing or not, at
' any opacity: "feed" fits it 16:9 in the body, "clip" shrinks it to a 2 px speck in the
' corner (the keep-awake clip only has to play), "hidden" takes it off the card.
sub placeVideo(how as string)
    m.video.visible = (how <> "hidden")
    if how = "feed" then
        fit = hkVideoFit(m.top.bodyW, m.top.bodyH)
        m.video.translation = [fit.x, fit.y]
        m.video.width = fit.w
        m.video.height = fit.h
        m.video.opacity = 1.0
    else
        m.video.translation = [0, 0]
        m.video.width = 2
        m.video.height = 2
    end if
end sub

sub showOffline(shown as boolean)
    m.offline.visible = shown
end sub

sub paintOffline()
    f = m.top.fonts
    bw = m.top.bodyW
    bh = m.top.bodyH
    m.offlineGlyph.uri = hkGlyphUri("cctv", 56)
    hkTint(m.offlineGlyph, HK_INK_FAINT())
    m.offlineGlyph.translation = [(bw - 56) \ 2, bh \ 2 - 56]
    if f <> invalid then m.offlineText.font = f.detail
    m.offlineText.color = HK_INK_MUTED()
    m.offlineText.width = bw
    m.offlineText.height = 32
    m.offlineText.translation = [0, bh \ 2 + 8]
end sub

' One event per change of state, so a retry loop doesn't flood the console.
sub report(state as string)
    if state = m.reported then return
    m.reported = state
    hkEvent("home_cam", { state: state, cam: m.cam, attempts: m.attempts })
end sub
