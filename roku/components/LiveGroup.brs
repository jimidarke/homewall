' LiveGroup: one camera full screen, with a supervisor that keeps its stream alive.
'
' Supervision, per camera:
'   - a player error or end-of-stream schedules a retry after hkNextBackoffSeconds(n),
'     where n counts that camera's consecutive failures (a flaky camera doesn't reset
'     the count of a healthy one, and switching cameras keeps both counts);
'   - every stallCheck tick, a camera that hasn't been "playing" for LIVE_STALL_S is
'     restarted from scratch;
'   - after LIVE_MAX_RETRIES failures in a row the streams map is probably stale, so
'     `rediscover` fires and MainScene runs discovery again;
'   - restartLong restarts a healthy stream before Roku OS stops it at 4 h.

function LIVE_MAX_RETRIES() as integer : return 4 : end function
function LIVE_STALL_S() as integer : return 90 : end function

sub init()
    m.player = m.top.findNode("player")
    m.hud = m.top.findNode("hud")
    m.liveTag = m.top.findNode("liveTag")
    m.curtain = m.top.findNode("retryCurtain")
    m.curtainTitle = m.top.findNode("retryTitle")
    m.curtainDetail = m.top.findNode("retryDetail")

    m.timers = {}
    for each id in ["hudHide", "stallCheck", "retryWait", "holdOk", "restartLong"]
        m.timers[id] = m.top.findNode(id)
    end for
    m.timers.restartLong.duration = HK_STREAM_REFRESH_S()

    m.player.observeField("state", "onPlayerState")
    m.timers.hudHide.observeField("fire", "hideHud")
    m.timers.stallCheck.observeField("fire", "onStallCheck")
    m.timers.retryWait.observeField("fire", "onRetryDue")
    m.timers.holdOk.observeField("fire", "onOkHeld")
    m.timers.restartLong.observeField("fire", "onRestartLong")

    m.failures = {}       ' cam -> consecutive failures
    m.healthyAt = 0       ' last time the player reported "playing" (or a start was issued)
    m.muted = {}          ' cam -> boolean, read from the registry on first use
    m.motionAt = {}       ' cam -> unix seconds of the last motion push
    m.dimmed = false
    ' OK can arrive as a lone release: entering from the home tile, HomeGroup consumed
    ' the press. Both flags must exist before the first key event.
    m.okDown = false
    m.okHeld = false

    m.top.findNode("liveBlink").control = "start"
    m.timers.stallCheck.control = "start"
    m.hud.cams = HK_CAMS().join(",")   ' the HUD pager takes the roster as a string
end sub

' ---------------------------------------------------------------------------
' Field handlers
' ---------------------------------------------------------------------------

sub onStreams()
    ' Discovery (re)arrived: a camera waiting for a URL can start now.
    if m.top.cam <> "" and m.player.state <> "playing" then playCam(0)
end sub

sub onCam()
    cam = m.top.cam
    if cam = "" then return
    hkEvent("cam_switch", { cam: cam })
    m.hud.cam = cam
    playCam(0)
    showHud()
end sub

sub onSwitch()
    req = m.top.requestSwitch
    if req = invalid or req.cam = invalid then return
    back = hkParseInt(req.replay)   ' goLive passes an integer; a string also works
    m.top.cam = req.cam              ' starts the camera via onCam
    if back > 0 then playCam(-back)
end sub

sub onMotion()
    push = m.top.motion
    if push = invalid or push.cam = invalid then return
    m.motionAt[push.cam] = hkParseInt(push.ts)
    if push.cam = m.top.cam then updateMotionLabel()
end sub

sub updateMotionLabel()
    at = m.motionAt[m.top.cam]
    if at = invalid then at = 0
    m.hud.motionLabel = hkMotionLabel(at, hkNowSeconds())
end sub

' ---------------------------------------------------------------------------
' Playback and supervision
' ---------------------------------------------------------------------------

' Starts the current camera; offsetSeconds < 0 seeks back into the HLS window.
sub playCam(offsetSeconds as integer)
    cam = m.top.cam
    if cam = "" then return
    streams = m.top.streams
    url = hkStreamUrl(streams, cam)
    if url = "" then
        hkLog("live: no URL for cam=" + cam + " yet")
        setCurtain(true, "Waiting for discovery…", "")
        return
    end if
    if streams[cam] = invalid or streams[cam].hls = invalid then
        hkLog("live: cam=" + cam + " missing from discovery, playing the mosaic")
    end if

    hkEvent("stream_start", { cam: cam, url: url, playStart: offsetSeconds })
    item = createObject("roSGNode", "ContentNode")
    item.url = url
    item.streamFormat = "hls"
    item.live = true
    if offsetSeconds <> 0 then item.playStart = offsetSeconds

    m.healthyAt = hkNowSeconds()
    m.player.mute = isMuted(cam)
    m.player.content = item
    m.player.control = "play"
    restartTimer(m.timers.restartLong)
end sub

sub onPlayerState()
    cam = m.top.cam
    state = m.player.state
    hkDebug("live: player " + state)
    if state = "playing" then
        m.healthyAt = hkNowSeconds()
        m.failures[cam] = 0
        m.hud.connected = "ok"
        setCurtain(false, "", "")
        hkEvent("stream_state", { cam: cam, state: state })
    else if state = "buffering" then
        m.hud.connected = "warn"
    else if state = "error" then
        hkEvent("stream_state", { cam: cam, state: state })
        failed("Stream error — retrying")
    else if state = "finished" then
        hkLog("live: cam=" + cam + " stream ended")
        failed("Source ended — retrying")
    end if
    ' "stopped" is what a camera switch or leaving the route looks like: nothing to do.
end sub

' One more consecutive failure for the current camera: wait and retry, or give up on
' the cached streams and ask for discovery.
sub failed(title as string)
    cam = m.top.cam
    n = 1
    if m.failures[cam] <> invalid then n = m.failures[cam] + 1
    m.failures[cam] = n
    m.hud.connected = "warn"
    m.player.control = "stop"

    if n > LIVE_MAX_RETRIES() then
        hkLog("live: cam=" + cam + " failed " + n.toStr() + " times, re-discovering")
        m.failures[cam] = 0
        setCurtain(true, title, "looking for the stream server")
        m.top.rediscover = true
        return
    end if

    pause = hkNextBackoffSeconds(n)
    hkLog("live: retry cam=" + cam + " #" + n.toStr() + " in " + pause.toStr() + "s")
    setCurtain(true, title, "attempt " + n.toStr() + " in " + pause.toStr() + "s")
    m.timers.retryWait.duration = pause
    restartTimer(m.timers.retryWait)
end sub

sub onRetryDue()
    playCam(0)
end sub

sub onStallCheck()
    updateMotionLabel()
    if m.top.cam = "" or m.player.state = "playing" then return
    idle = hkNowSeconds() - m.healthyAt
    if idle > LIVE_STALL_S() then
        hkLog("live: no playback for " + idle.toStr() + "s (state=" + m.player.state + "), restarting")
        m.failures[m.top.cam] = 0
        m.player.control = "stop"
        playCam(0)
    end if
end sub

' Roku OS stops a stream 4 h after it started if the remote is untouched. Restart a
' healthy one before then; a stopped player (home, or the grid has the decoder) stays put.
sub onRestartLong()
    state = m.player.state
    if m.top.cam = "" or (state <> "playing" and state <> "buffering") then return
    hkEvent("stream_refresh", { cam: m.top.cam })
    m.player.control = "stop"
    playCam(0)
end sub

sub setCurtain(visible as boolean, title as string, detail as string)
    m.curtain.visible = visible
    m.curtainTitle.text = title
    m.curtainDetail.text = detail
end sub

sub restartTimer(t as object)
    t.control = "stop"
    t.control = "start"
end sub

' ---------------------------------------------------------------------------
' HUD, audio, dimming
' ---------------------------------------------------------------------------

sub showHud()
    m.hud.visibleHud = true
    restartTimer(m.timers.hudHide)
end sub

sub hideHud()
    m.hud.visibleHud = false
end sub

' Audio is muted unless the user unmuted this camera before (persisted per camera).
function isMuted(cam as string) as boolean
    if m.muted[cam] = invalid then m.muted[cam] = (regRead(HK_REG_KEY_AUDIO_PREFIX() + cam) <> "0")
    return m.muted[cam]
end function

sub toggleMute()
    cam = m.top.cam
    muted = not isMuted(cam)
    m.muted[cam] = muted
    value = "0"
    if muted then value = "1"
    regWrite(HK_REG_KEY_AUDIO_PREFIX() + cam, value)
    m.player.mute = muted
    showHud()
end sub

sub toggleDim()
    m.dimmed = not m.dimmed
    if m.dimmed then
        m.liveTag.opacity = 0.3
        hideHud()
    else
        m.liveTag.opacity = 1.0
        showHud()
    end if
end sub

sub stepCam(delta as integer)
    roster = HK_CAMS()
    n = roster.count()
    i = (hkCamIndex(m.top.cam, roster) + delta + n) mod n
    m.top.cam = roster[i]
end sub

' ---------------------------------------------------------------------------
' Remote
' ---------------------------------------------------------------------------

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then
        if key = "OK" then
            m.timers.holdOk.control = "stop"
            if m.okDown and not m.okHeld then toggleHud()
            m.okDown = false
            m.okHeld = false
        end if
        return false
    end if

    if key = "OK" then
        m.okDown = true
        m.okHeld = false
        restartTimer(m.timers.holdOk)
    else if key = "left" then
        stepCam(-1)
    else if key = "right" then
        stepCam(1)
    else if key = "up" or key = "down" then
        showHud()
    else if key = "replay" or key = "instantreplay" then
        playCam(-15)
    else if key = "options" then
        toggleMute()
    else if key = "info" then
        toggleDim()
    else
        return false
    end if
    return true
end function

sub onOkHeld()
    if not m.okDown then return
    m.okHeld = true
    m.top.requestGrid = true
end sub

sub toggleHud()
    if m.hud.visibleHud then hideHud() else showHud()
end sub
