' OverlayLayer — info-overlay framework (v0.5).
'
' Public API:
'   show(params)    — render an overlay; params is the parsed ECP /input map.
'                     Required: params.overlay = "door" | "weather" | "sensor"
'                     | "pip" | "text". Unknown kinds are ignored.
'   hide()          — dismiss every visible overlay (used on mode change).
'
' Each zone (topBanner, weather, sensor, pip) has independent state and timer.
' Calling show() against a zone that's already visible replaces its content
' and restarts its dismiss timer — no queueing.

sub init()
    m.topFade        = m.top.findNode("topFade")
    m.topFadeIn      = m.top.findNode("topFadeIn")
    m.topFadeOut     = m.top.findNode("topFadeOut")

    m.topBanner      = m.top.findNode("topBanner")
    m.topBannerStripe= m.top.findNode("topBannerStripe")
    m.topBannerTitle = m.top.findNode("topBannerTitle")
    m.topBannerSub   = m.top.findNode("topBannerSub")
    m.topBannerIn    = m.top.findNode("topBannerSlideIn")
    m.topBannerOut   = m.top.findNode("topBannerSlideOut")
    m.topBannerTimer = m.top.findNode("topBannerTimer")
    m.topBannerTimer.observeField("fire", "onTopBannerExpire")
    m.topBannerOut.observeField("state", "onTopBannerOutDone")

    m.weather        = m.top.findNode("weatherChip")
    m.weatherIcon    = m.top.findNode("weatherIcon")
    m.weatherTemp    = m.top.findNode("weatherTemp")
    m.weatherSub     = m.top.findNode("weatherSub")
    m.weatherIn      = m.top.findNode("weatherSlideIn")
    m.weatherOut     = m.top.findNode("weatherSlideOut")
    m.weatherTimer   = m.top.findNode("weatherTimer")
    m.weatherTimer.observeField("fire", "onWeatherExpire")
    m.weatherOut.observeField("state", "onWeatherOutDone")

    m.sensor         = m.top.findNode("sensorChip")
    m.sensorIcon     = m.top.findNode("sensorIcon")
    m.sensorValue    = m.top.findNode("sensorValue")
    m.sensorSub      = m.top.findNode("sensorSub")
    m.sensorIn       = m.top.findNode("sensorSlideIn")
    m.sensorOut      = m.top.findNode("sensorSlideOut")
    m.sensorTimer    = m.top.findNode("sensorTimer")
    m.sensorTimer.observeField("fire", "onSensorExpire")
    m.sensorOut.observeField("state", "onSensorOutDone")

    m.pipBox         = m.top.findNode("pipBox")
    m.pipImage       = m.top.findNode("pipImage")
    m.pipLabel       = m.top.findNode("pipLabel")
    m.pipCountdown   = m.top.findNode("pipCountdown")
    m.pipIn          = m.top.findNode("pipSlideIn")
    m.pipOut         = m.top.findNode("pipSlideOut")
    m.pipTimer       = m.top.findNode("pipTimer")
    m.pipTickTimer   = m.top.findNode("pipCountdownTimer")
    m.pipTimer.observeField("fire", "onPipExpire")
    m.pipOut.observeField("state", "onPipOutDone")
    m.pipTickTimer.observeField("fire", "onPipTick")

    m.weatherVisible = false
    m.sensorVisible  = false
    m.pipTask        = invalid
    m.pipDeadlineMs  = 0
    m.pipTimespan    = createObject("roTimespan")
end sub

' ---------------------------------------------------------------------------
' Public: show / hide
' ---------------------------------------------------------------------------

function show(params as object) as boolean
    if params = invalid then return false
    kind = params.overlay
    if kind = invalid or kind = "" then return false

    if kind = "door"    then return showTopBanner(params, "door")
    if kind = "text"    then return showTopBanner(params, "text")
    if kind = "weather" then return showWeather(params)
    if kind = "sensor"  then return showSensor(params)
    if kind = "pip"     then return showPip(params)

    hkLog("OverlayLayer: ignoring unknown overlay kind=" + kind)
    return false
end function

function hide() as boolean
    dismissTopBanner()
    dismissWeather()
    dismissSensor()
    dismissPip()
    return true
end function

' ---------------------------------------------------------------------------
' Top banner (door / text)
' ---------------------------------------------------------------------------

function showTopBanner(params as object, kind as string) as boolean
    severity = params.severity
    if severity = invalid then severity = "normal"

    title = ""
    sub_  = ""
    if kind = "door" then
        label = params.label
        if label = invalid or label = "" then label = "Door"
        action = params.action
        if action = invalid or action = "" then action = "event"
        title = UCase(label) + " · " + UCase(action)
        if params.detail <> invalid and params.detail <> "" then
            sub_ = params.detail
        else
            sub_ = "just now"
        end if
    else
        ' "text" kind
        if params.banner <> invalid then title = params.banner
        if params.detail <> invalid then sub_ = params.detail
        if title = "" and params.label <> invalid then title = params.label
    end if

    m.topBannerTitle.text = title
    m.topBannerSub.text   = sub_
    m.topBannerStripe.color = hkSeverityColor(severity)

    ttlMs = hkOverlayDurationMs(kind, params)
    m.topBannerTimer.control = "stop"
    m.topBannerTimer.duration = ttlMs / 1000
    m.topBannerTimer.control = "start"

    m.topBannerOut.control = "stop"
    m.topBannerIn.control  = "start"
    hkEvent("overlay_show", { kind: kind, sev: severity, ttlMs: ttlMs })
    return true
end function

sub onTopBannerExpire() : dismissTopBanner() : end sub

sub dismissTopBanner()
    m.topBannerTimer.control = "stop"
    m.topBannerIn.control = "stop"
    m.topBannerOut.control = "start"
end sub

sub onTopBannerOutDone()
    if m.topBannerOut.state <> "stopped" then return
    m.topBannerTitle.text = ""
    m.topBannerSub.text = ""
end sub

' ---------------------------------------------------------------------------
' Weather chip
' ---------------------------------------------------------------------------

function showWeather(params as object) as boolean
    icon = "*"
    cond = params.cond
    if cond = invalid then cond = ""
    icon = weatherIconFor(cond)

    temp = params.temp
    hi = params.hi
    if temp = invalid then temp = "?"
    tempStr = temp.toStr() + "°"
    if hi <> invalid and hi.toStr() <> "" then tempStr = tempStr + "  hi " + hi.toStr() + "°"

    m.weatherIcon.text = icon
    m.weatherTemp.text = tempStr
    m.weatherSub.text  = cond

    ttlMs = hkOverlayDurationMs("weather", params)
    m.weatherTimer.control = "stop"
    m.weatherTimer.duration = ttlMs / 1000
    m.weatherTimer.control = "start"

    m.weatherOut.control = "stop"
    m.weatherIn.control  = "start"
    setWeatherVisible(true)
    hkEvent("overlay_show", { kind: "weather", ttlMs: ttlMs })
    return true
end function

sub onWeatherExpire() : dismissWeather() : end sub

sub dismissWeather()
    m.weatherTimer.control = "stop"
    m.weatherIn.control = "stop"
    m.weatherOut.control = "start"
end sub

sub onWeatherOutDone()
    if m.weatherOut.state <> "stopped" then return
    m.weatherIcon.text = ""
    m.weatherTemp.text = ""
    m.weatherSub.text = ""
    setWeatherVisible(false)
end sub

' ---------------------------------------------------------------------------
' Sensor chip
' ---------------------------------------------------------------------------

function showSensor(params as object) as boolean
    iconKey = params.icon
    if iconKey = invalid then iconKey = ""
    value = params.value
    if value = invalid then value = "?"
    sub_ = ""
    if params.label <> invalid then sub_ = params.label

    m.sensorIcon.text  = sensorIconFor(iconKey)
    m.sensorValue.text = value
    m.sensorSub.text   = sub_

    ttlMs = hkOverlayDurationMs("sensor", params)
    m.sensorTimer.control = "stop"
    m.sensorTimer.duration = ttlMs / 1000
    m.sensorTimer.control = "start"

    m.sensorOut.control = "stop"
    m.sensorIn.control  = "start"
    setSensorVisible(true)
    hkEvent("overlay_show", { kind: "sensor", ttlMs: ttlMs })
    return true
end function

sub onSensorExpire() : dismissSensor() : end sub

sub dismissSensor()
    m.sensorTimer.control = "stop"
    m.sensorIn.control = "stop"
    m.sensorOut.control = "start"
end sub

sub onSensorOutDone()
    if m.sensorOut.state <> "stopped" then return
    m.sensorIcon.text = ""
    m.sensorValue.text = ""
    m.sensorSub.text = ""
    setSensorVisible(false)
end sub

' ---------------------------------------------------------------------------
' PIP — JPEG snapshot loop
' ---------------------------------------------------------------------------

function showPip(params as object) as boolean
    cam = params.cam
    if cam = invalid or cam = "" then return false

    serverBase = params.serverBase
    if serverBase = invalid or serverBase = "" then serverBase = HK_OVERLAY_SNAPSHOT_BASE()

    m.pipLabel.text = UCase(HK_CAM_DISPLAY_NAME(cam))

    ttlMs = hkOverlayDurationMs("pip", params)
    m.pipDeadlineMs = ttlMs
    m.pipTimespan.mark()
    m.pipCountdown.text = (ttlMs / 1000).toStr() + "s"
    m.pipTimer.control = "stop"
    m.pipTimer.duration = ttlMs / 1000
    m.pipTimer.control = "start"
    m.pipTickTimer.control = "stop"
    m.pipTickTimer.control = "start"

    ' Spin up a fresh fetcher task. Stop any previous one first.
    stopPipTask()
    m.pipTask = createObject("roSGNode", "JpegPipTask")
    m.pipTask.cam = cam
    m.pipTask.serverBase = serverBase
    m.pipTask.intervalMs = HK_OVERLAY_PIP_INTERVAL_MS()
    m.pipTask.observeField("frameUri", "onPipFrame")
    m.pipTask.control = "RUN"

    m.pipOut.control = "stop"
    m.pipIn.control  = "start"
    hkEvent("overlay_show", { kind: "pip", cam: cam, ttlMs: ttlMs })
    return true
end function

sub onPipFrame()
    if m.pipTask = invalid then return
    uri = m.pipTask.frameUri
    if uri <> invalid and uri <> "" then m.pipImage.uri = uri
end sub

sub onPipTick()
    if m.pipDeadlineMs <= 0 then return
    remainingMs = m.pipDeadlineMs - m.pipTimespan.totalMilliseconds()
    if remainingMs < 0 then remainingMs = 0
    m.pipCountdown.text = ((remainingMs + 500) / 1000).toStr() + "s"
end sub

sub onPipExpire() : dismissPip() : end sub

sub dismissPip()
    stopPipTask()
    m.pipTimer.control = "stop"
    m.pipTickTimer.control = "stop"
    m.pipIn.control = "stop"
    m.pipOut.control = "start"
end sub

sub onPipOutDone()
    if m.pipOut.state <> "stopped" then return
    m.pipImage.uri = ""
    m.pipLabel.text = ""
    m.pipCountdown.text = ""
end sub

sub stopPipTask()
    if m.pipTask = invalid then return
    m.pipTask.unobserveField("frameUri")
    m.pipTask.control = "stop"
    m.pipTask = invalid
end sub

' ---------------------------------------------------------------------------
' Top-fade ticker — visible whenever any chip is up.
' ---------------------------------------------------------------------------

sub setWeatherVisible(v as boolean)
    m.weatherVisible = v
    refreshTopFade()
end sub

sub setSensorVisible(v as boolean)
    m.sensorVisible = v
    refreshTopFade()
end sub

sub refreshTopFade()
    wantVisible = m.weatherVisible or m.sensorVisible
    if wantVisible then
        m.topFadeOut.control = "stop"
        m.topFadeIn.control = "start"
    else
        m.topFadeIn.control = "stop"
        m.topFadeOut.control = "start"
    end if
end sub

' ---------------------------------------------------------------------------
' Glyph helpers
' ---------------------------------------------------------------------------

' Roku's bundled fonts don't carry colour emoji, but the unicode glyphs do
' render in the system font as monochrome shapes — readable enough at chip
' size and zero new assets. Fall back to ASCII for unknown.
function weatherIconFor(cond as string) as string
    c = LCase(cond)
    if Instr(1, c, "snow")  > 0 then return "❄"
    if Instr(1, c, "rain")  > 0 then return "☂"
    if Instr(1, c, "storm") > 0 then return "⚡"
    if Instr(1, c, "cloud") > 0 then return "☁"
    if Instr(1, c, "fog")   > 0 then return "≈"
    if Instr(1, c, "clear") > 0 then return "☀"
    if Instr(1, c, "sun")   > 0 then return "☀"
    return "·"
end function

function sensorIconFor(key as string) as string
    k = LCase(key)
    if k = "bolt"  or k = "energy" or k = "power" then return "⚡"
    if k = "water" or k = "drop"   or k = "flow"  then return "💧"
    if k = "temp"  or k = "thermo"                 then return "°"
    if k = "wind"                                  then return "≋"
    if k = "door"                                  then return "▢"
    return "·"
end function
