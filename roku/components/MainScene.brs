' MainScene — route router for HAku.
'   Routes: home (glass wall, default; OK opens the picker) · picker (camera list over
'           home) · live (fullscreen camera) · grid (2x2) · module (drill-down, no longer
'           reached from home) · diag (status). Owns discovery, the
'           sidecar poll, ECP fan-out, overlays, toasts, and idle/auto-takeover.
' Live video is gated by LiveGroup.cam: home/module/diag leave it "" so the single
' H.264 decoder is free. On home the camera card's feed (HomeGroup.camActive) holds it
' when there is one; otherwise, and on module/diag, a hidden keep-awake Video plays
' instead to stop the OS screensaver taking over (Roku exposes no API to disable it;
' any playback suppresses it). Whatever holds the decoder is stopped before anything
' else plays, preserving the one-decoder budget (syncHomeDecoder). The rotating
' BackgroundGallery covers burn-in.

sub init()
    m.configPending = false     ' startHubPoll(true) until a config arrives
    m.pollFailed = false
    m.lastPollLog = 0
    m.home           = m.top.findNode("home")
    m.live           = m.top.findNode("live")
    m.grid           = m.top.findNode("grid")
    m.moduleScreen   = m.top.findNode("moduleScreen")
    m.diag           = m.top.findNode("diag")
    m.picker         = m.top.findNode("picker")
    m.overlays       = m.top.findNode("overlays")
    m.toast          = m.top.findNode("toast")
    m.bgGallery      = m.top.findNode("bgGallery")
    m.bgDim          = m.top.findNode("bgDim")
    m.keepAwake      = m.top.findNode("keepAwake")
    m.discover       = m.top.findNode("discover")
    m.inputPump      = m.top.findNode("inputPump")
    m.modules        = m.top.findNode("modules")
    m.bgList         = m.top.findNode("bgList")
    m.diagHealth     = m.top.findNode("diagHealth")
    m.rediscoverTimer = m.top.findNode("rediscoverTimer")
    m.stateTimer     = m.top.findNode("stateTimer")
    m.idleTimer      = m.top.findNode("idleTimer")
    m.returnHomeTimer = m.top.findNode("returnHomeTimer")
    m.homeCamTimer   = m.top.findNode("homeCamTimer")
    m.keepAwakeWatchdog = m.top.findNode("keepAwakeWatchdog")
    m.bgListTimer    = m.top.findNode("bgListTimer")

    m.discover.observeField("result", "onDiscoveryResult")
    m.inputPump.observeField("event", "onInputEvent")
    m.rediscoverTimer.observeField("fire", "onRediscoverFire")
    m.live.observeField("requestGrid", "onRequestGrid")
    m.live.observeField("streams", "onLiveStreamsCleared")
    m.grid.observeField("selectedCam", "onGridSelected")
    m.grid.observeField("cancel", "onGridCancel")
    m.modules.observeField("config", "onModuleConfig")
    m.modules.observeField("snapshot", "onModuleSnapshot")
    m.bgList.observeField("result", "onBgList")
    m.diagHealth.observeField("result", "onDiagHealth")
    m.diag.observeField("dismiss", "onDiagDismiss")
    m.picker.observeField("selected", "onPickerSelected")
    m.keepAwake.observeField("state", "onKeepAwakeState")
    m.home.observeField("hasCam", "onHomeHasCam")
    m.stateTimer.observeField("fire", "onStateTimer")
    m.idleTimer.observeField("fire", "onIdleTimer")
    m.returnHomeTimer.observeField("fire", "onReturnHomeTimer")
    m.homeCamTimer.observeField("fire", "onHomeCamTimer")
    m.keepAwakeWatchdog.observeField("fire", "onKeepAwakeWatchdog")
    m.bgListTimer.observeField("fire", "runBgList")

    m.route = "home"
    m.config = invalid
    m.lastSnapshot = invalid
    m.hubBase = ""
    m.host = ""
    m.schemaVersion = ""
    m.streamCount = 0
    m.takeoverActive = false
    m.manualLive = false        ' a camera picked from the OK list: no idle return
    m.keepAwakeOn = false

    ' Keep-awake decoder content (a tiny silent black loop). Built once; play/stop
    ' toggled by route. Looping is manual (Video has no loop field) via onKeepAwakeState.
    kc = createObject("roSGNode", "ContentNode")
    kc.url = "pkg:/images/keepawake.mp4"
    kc.streamFormat = "mp4"
    m.keepAwake.content = kc
    m.keepAwake.mute = true

    m.modules.layout = HK_LAYOUT()
    regDelete(HK_REG_KEY_CONFIG_OLD())   ' pre-0.11 default-view cache: never read again

    m.idleTimer.duration = HK_IDLE_TO_HOME_MS() / 1000
    m.returnHomeTimer.duration = HK_RETURN_HOME_MS() / 1000
    m.homeCamTimer.duration = HK_HOME_CAM_MAX_MS() / 1000
    m.stateTimer.duration = hkStatePollMsFor(createObject("roDeviceInfo").getModel()) / 1000
    m.bgListTimer.duration = HK_BG_LIST_MS() / 1000
    m.bgListTimer.control = "start"

    ' Input pump must run immediately so hot ECP relaunches arrive before discovery.
    m.inputPump.control = "RUN"

    ' Cached fast-paths (present home + streams instantly on cold boot).
    cachedStreams = readCachedStreams()
    if cachedStreams <> invalid then
        m.live.streams = cachedStreams
        m.grid.streams = cachedStreams
        m.home.streams = cachedStreams
    end if
    cachedCfg = readCachedConfig()
    if cachedCfg <> invalid then
        m.config = cachedCfg
        m.home.config = cachedCfg
        m.bgGallery.intervalMs = hkBgRotateMs(cachedCfg)
    end if
    cachedBase = hkHubBase()
    if cachedBase <> "" then
        m.hubBase = cachedBase
        m.modules.hubBase = cachedBase
        m.home.hubBase = cachedBase
        startHubPoll(true)
        runBgList()
    end if

    ' Default cam for when the user enters live (do NOT start playback here).
    initialCam = regRead(HK_REG_KEY_DEFAULT_CAM())
    if initialCam = "" then initialCam = HK_CAMS()[0]
    m.lastLiveCam = initialCam

    m.discover.control = "RUN"
    goHome()
end sub

' ---------------------------------------------------------------------------
' Args (deep-link)
' ---------------------------------------------------------------------------
sub onArgs()
    args = m.top.args
    if args = invalid then return

    if args.haToken <> invalid and args.haToken <> "" then
        regWrite(HK_REG_KEY_HA_TOKEN(), args.haToken)
        haUrlVal = "(unchanged)"
        if args.haUrl <> invalid then
            regWrite(HK_REG_KEY_HA_URL(), args.haUrl)
            haUrlVal = args.haUrl
        end if
        showToast("Connected to Home Assistant", "low", 2000)
        hkEvent("ha_bootstrap", { haToken: "REDACTED", haUrl: haUrlVal })
    end if

    if args.hubBase <> invalid and args.hubBase <> "" then
        hkSetHubBase(args.hubBase)
        m.hubBase = args.hubBase
        m.modules.hubBase = args.hubBase
        m.home.hubBase = args.hubBase
        startHubPoll(true)
    end if

    if args.setDefault <> invalid and args.setDefault <> "" then
        regWrite(HK_REG_KEY_DEFAULT_CAM(), args.setDefault)
        showToast("Default cam: " + HK_CAM_DISPLAY_NAME(args.setDefault), "low", 2000)
        m.lastLiveCam = args.setDefault
    end if

    ' Cold-launch routing / events.
    if args.overlay <> invalid or args.cam <> invalid or args.severity <> invalid or args.mode <> invalid or args.focusModule <> invalid or args.homeCam <> invalid then
        dispatchEcp(args)
    end if
end sub

' ---------------------------------------------------------------------------
' Discovery
' ---------------------------------------------------------------------------
sub onDiscoveryResult()
    r = m.discover.result
    if r = invalid then return

    if r.ok = true then
        hkEvent("discovery_ok", { streams: streamsKeys(r.streams), host: r.host, schemaVersion: r.schemaVersion })
        m.live.streams = r.streams
        m.grid.streams = r.streams
        m.home.streams = r.streams
        writeCachedStreams(r.streams)

        ' Telemetry surfaced by the diagnostic screen.
        m.streamCount = streamCountOf(r.streams)
        if r.schemaVersion <> invalid then m.schemaVersion = r.schemaVersion.toStr()
        if r.host <> invalid and r.host <> "" then m.host = r.host.toStr()

        if r.sidecar <> invalid and r.sidecar.base <> invalid and r.sidecar.base <> "" then
            m.hubBase = r.sidecar.base
            hkSetHubBase(r.sidecar.base)
            m.modules.hubBase = r.sidecar.base
            m.home.hubBase = r.sidecar.base
            startHubPoll(true)
            runBgList()
        end if
    else
        err = r.error
        if err = invalid then err = "(unknown)"
        hkEvent("discovery_failed", { err: err })
        m.rediscoverTimer.control = "stop"
        m.rediscoverTimer.control = "start"
    end if
end sub

sub onRediscoverFire()
    m.discover.control = "RUN"
end sub

sub onLiveStreamsCleared()
    streams = m.live.streams
    if streams = invalid then return
    has = false
    for each k in streams
        has = true
        exit for
    end for
    if not has then
        hkLog("LiveGroup escalated to re-discovery")
        clearCachedStreams()
        m.discover.control = "RUN"
    end if
end sub

function streamsKeys(streams as object) as string
    parts = []
    for each k in streams
        parts.push(k)
    end for
    return parts.join(",")
end function

function streamCountOf(streams as object) as integer
    n = 0
    if streams = invalid then return 0
    for each k in streams
        n = n + 1
    end for
    return n
end function

' ---------------------------------------------------------------------------
' Sidecar poll
' ---------------------------------------------------------------------------
' A config fetch stays pending until a config arrives: a RUN sent while the Task is
' still busy is dropped, and at a 1 s poll the next tick must ask for it again.
sub startHubPoll(fetchConfig as boolean)
    if m.hubBase = "" then return
    if fetchConfig then m.configPending = true
    m.modules.fetchConfig = m.configPending
    m.modules.control = "RUN"
    m.stateTimer.control = "start"
end sub

sub onStateTimer()
    if m.hubBase = "" then return
    m.modules.fetchConfig = m.configPending
    m.modules.control = "RUN"
end sub

sub onModuleConfig()
    cfg = m.modules.config
    if cfg = invalid or cfg.modules = invalid then return
    m.configPending = false
    m.config = cfg
    m.home.config = cfg
    m.bgGallery.intervalMs = hkBgRotateMs(cfg)
    writeCachedConfig(cfg)
    hkEvent("config_ok", { modules: moduleIds(cfg) })
end sub

' Kick the background-list task at the current hub base (at boot, on discovery, and
' every HK_BG_LIST_MS). Its result feeds BackgroundGallery.images, which keeps its
' photos when a refresh comes back empty.
sub runBgList()
    if m.hubBase = "" then return
    m.bgList.hubBase = m.hubBase
    m.bgList.control = "RUN"
end sub

sub onBgList()
    urls = m.bgList.result
    if urls = invalid then return
    m.bgGallery.images = urls
end sub

sub onModuleSnapshot()
    snap = m.modules.snapshot
    if snap = invalid then return
    m.home.fetched = true                ' a fetch finished: the header stops "connecting"
    if snap.err = "unknown_layout" then
        startHubPoll(true)               ' the sidecar lost the layout: re-fetch config
        return
    end if
    if snap.ts = invalid then            ' error payloads carry no ts
        if not m.pollFailed then hkEvent("poll_fail", { err: snap.err })
        m.pollFailed = true
        return
    end if
    m.lastSnapshot = snap
    m.home.state = snap
    now = hkNowSeconds()
    m.home.lastOk = now
    if m.route = "module" then refreshModuleScreen()
    if hkPollLogDue(m.lastPollLog, now, m.pollFailed) then
        hkEvent("poll_ok", { ts: snap.ts })
        m.lastPollLog = now
    end if
    m.pollFailed = false
end sub

function moduleIds(cfg as object) as string
    ids = []
    for each md in cfg.modules
        if md.id <> invalid then ids.push(md.id)
    end for
    return ids.join(",")
end function

' ---------------------------------------------------------------------------
' Module lookup (HA takeovers)
' ---------------------------------------------------------------------------
function moduleById(id as string) as object
    if m.config = invalid or m.config.modules = invalid then return invalid
    for each md in m.config.modules
        if md.id = id then return md
    end for
    return invalid
end function

function isCameraModule(md as object) as boolean
    if md.kind = "cameras" then return true
    if md.drill <> invalid and md.drill.route = "live" then return true
    return false
end function

function feedValues(md as object) as object
    if m.lastSnapshot = invalid then return invalid
    fk = md.id
    if md.feedKey <> invalid then fk = md.feedKey
    if fk <> invalid and m.lastSnapshot.doesExist(fk) then return m.lastSnapshot[fk]
    return invalid
end function

sub refreshModuleScreen()
    if m.moduleScreen.descriptor = invalid then return
    md = m.moduleScreen.descriptor
    vals = feedValues(md)
    if vals <> invalid then m.moduleScreen.values = vals
    if m.lastSnapshot <> invalid and m.lastSnapshot.ts <> invalid then
        m.moduleScreen.cacheBust = m.lastSnapshot.ts.toStr()
    end if
end sub

' ---------------------------------------------------------------------------
' Route transitions
' ---------------------------------------------------------------------------
sub goHome()
    stopLivePlayer()
    m.live.cam = ""
    m.live.visible = false
    m.grid.active = false
    m.grid.visible = false
    m.moduleScreen.visible = false
    m.diag.visible = false
    m.picker.visible = false
    setBackdrop(true)
    m.home.visible = true
    m.home.setFocus(true)
    m.route = "home"
    syncHomeDecoder()
    m.takeoverActive = false
    m.manualLive = false
    m.returnHomeTimer.control = "stop"
    resetIdle()
    hkEvent("route", { to: "home" })
end sub

' Rotating photo backdrop + light scrim: on for the passive routes (home/module/
' diag), off under live/grid where a video fills the screen (frees the textures).
sub setBackdrop(active as boolean)
    m.bgGallery.active = active
    m.bgDim.visible = active
end sub

sub goLive(cam as string, replaySeconds as integer)
    if cam = "" then cam = m.lastLiveCam
    if cam = "" then cam = HK_CAMS()[0]
    m.home.camActive = false     ' free the decoder before the live player claims it
    stopKeepAwake()
    setBackdrop(false)
    m.home.visible = false
    m.moduleScreen.visible = false
    m.diag.visible = false
    m.picker.visible = false
    if m.route = "grid" then
        m.grid.active = false
        m.grid.visible = false
    end if
    m.live.visible = true
    m.live.setFocus(true)
    m.route = "live"
    if replaySeconds > 0 then
        m.live.requestSwitch = { cam: cam, replay: replaySeconds }
    else
        m.live.cam = cam
    end if
    m.lastLiveCam = cam
    resetIdle()
    hkEvent("route", { to: "live", cam: cam })
end sub

sub goModule(md as object)
    stopLivePlayer()
    m.live.cam = ""
    m.live.visible = false
    m.grid.active = false
    m.grid.visible = false
    m.home.visible = false
    m.home.camActive = false
    m.diag.visible = false
    setBackdrop(true)
    startKeepAwake()
    m.moduleScreen.descriptor = md
    m.moduleScreen.hubBase = m.hubBase
    vals = feedValues(md)
    if vals <> invalid then m.moduleScreen.values = vals
    if m.lastSnapshot <> invalid and m.lastSnapshot.ts <> invalid then
        m.moduleScreen.cacheBust = m.lastSnapshot.ts.toStr()
    end if
    m.moduleScreen.visible = true
    m.moduleScreen.callFunc("takeFocus")   ' agenda drills focus their list to scroll
    m.route = "module"
    resetIdle()
    hkEvent("route", { to: "module", id: md.id })
end sub

sub stopLivePlayer()
    p = m.live.findNode("player")
    if p <> invalid then p.control = "stop"
end sub

' ---------------------------------------------------------------------------
' GRID (reached from LIVE via long-press OK)
' ---------------------------------------------------------------------------
sub onRequestGrid()
    if m.live.requestGrid then enterGrid()
end sub

sub enterGrid()
    if m.route = "grid" then return
    hkEvent("route", { to: "grid" })
    m.grid.setFocus(true)
    stopLivePlayer()
    m.home.camActive = false     ' single-decoder budget: free it before the mosaic plays
    stopKeepAwake()
    setBackdrop(false)
    m.live.visible = false
    m.home.visible = false
    m.grid.visible = true
    m.grid.active = true
    m.route = "grid"
    resetIdle()
end sub

sub onGridSelected()
    cam = m.grid.selectedCam
    if cam = "" then return
    goLive(cam, 0)
end sub

sub onGridCancel()
    if not m.grid.cancel then return
    goLive(m.lastLiveCam, 0)
end sub

' ---------------------------------------------------------------------------
' PICKER (reached from HOME via OK): pick a camera to watch full screen
' ---------------------------------------------------------------------------
' Opens over home, whose camera card keeps the decoder until a camera is chosen.
sub goPicker()
    cams = hkPickerCams(m.live.streams)
    if cams.count() = 0 then
        showToast("No cameras yet", "low", 2500)
        return
    end if
    m.picker.cams = cams
    m.picker.visible = true
    m.picker.callFunc("takeFocus")
    m.route = "picker"
    resetIdle()
    hkEvent("picker_open", { cams: cams.count() })
end sub

' A camera picked by hand stays up until Back (resetIdle skips it).
sub onPickerSelected()
    cam = m.picker.selected
    if cam = "" then return
    hkEvent("picker_select", { cam: cam })
    m.manualLive = true
    goLive(cam, 0)
end sub

' ---------------------------------------------------------------------------
' DIAG (reached from HOME via the * / options button)
' ---------------------------------------------------------------------------
sub goDiag()
    ' Build info first so a surprise roDeviceInfo hiccup can't leave us on a bare
    ' backdrop with home already hidden.
    dev = buildDeviceInfo()
    disc = buildDiscoveryInfo()
    m.diag.device = dev
    m.diag.discovery = disc
    m.home.visible = false
    m.home.camActive = false
    m.moduleScreen.visible = false
    setBackdrop(true)
    startKeepAwake()
    m.diag.visible = true
    m.diag.setFocus(true)
    m.route = "diag"
    if m.hubBase <> "" then
        m.diagHealth.hubBase = m.hubBase
        m.diagHealth.control = "RUN"
    else
        m.diag.health = { reachable: false, base: "" }
    end if
    resetIdle()
    hkEvent("route", { to: "diag" })
end sub

function buildDeviceInfo() as object
    di = createObject("roDeviceInfo")

    osStr = ""
    osMajor = 0
    os = di.GetOSVersion()
    if os <> invalid then
        osMajor = hkParseInt(os.major)
        osStr = so(os.major) + "." + so(os.minor) + "." + so(os.revision)
        if os.build <> invalid then osStr = osStr + " (" + os.build.toStr() + ")"
    end if

    ' Uptime is Roku OS 15.0+; guard the call so older firmware doesn't crash.
    uptime = "—"
    if osMajor >= 15 then uptime = hkUptimeLabel(di.GetUptimeMillisecondsAsLong())

    netStr = connectionLabel(di.GetConnectionType())
    ci = di.GetConnectionInfo()
    if ci <> invalid and ci.ssid <> invalid and ci.ssid.toStr() <> "" then
        netStr = netStr + " · " + ci.ssid.toStr()
    end if

    return {
        friendly: di.GetFriendlyName()
        model:    di.GetModelDisplayName()
        os:       osStr
        ip:       firstIpAddr(di.GetIPAddrs())
        network:  netStr
        memory:   di.GetGeneralMemoryLevel()
        uptime:   uptime
    }
end function

function buildDiscoveryInfo() as object
    sidecar = m.hubBase
    if sidecar = "" then sidecar = "(not discovered)"
    host = m.host
    if host = "" then host = "(unknown)"
    schema = m.schemaVersion
    if schema = "" then schema = "—"
    return {
        sidecar: sidecar
        host:    host
        schema:  "v" + schema
        streams: m.streamCount.toStr()
    }
end function

function firstIpAddr(ips as object) as string
    if ips = invalid then return "—"
    for each k in ips
        v = ips[k]
        if v <> invalid and v.toStr() <> "" and v.toStr() <> "0.0.0.0" then return v.toStr()
    end for
    return "—"
end function

function connectionLabel(conn as dynamic) as string
    if conn = "WiredConnection" then return "Wired"
    if conn = "WiFiConnection" then return "Wi-Fi"
    if conn = invalid or conn = "" then return "Offline"
    return conn.toStr()
end function

sub onDiagHealth()
    if m.diagHealth.result <> invalid then m.diag.health = m.diagHealth.result
end sub

sub onDiagDismiss()
    if m.diag.dismiss then goHome()
end sub

function so(v as dynamic) as string
    if v = invalid then return "—"
    s = v.toStr()
    if s = "" then return "—"
    return s
end function

' ---------------------------------------------------------------------------
' Keep-awake decoder (screensaver suppression on home/module/diag)
' ---------------------------------------------------------------------------

' On home the camera card's feed holds the decoder when there is one (its playback
' keeps the screensaver away, and while it rests it plays the keep-awake clip itself);
' otherwise the keep-awake clip does. One stops before the other starts.
sub syncHomeDecoder()
    if m.home.hasCam then
        stopKeepAwake()
        m.home.camActive = true
    else
        m.home.camActive = false
        startKeepAwake()
    end if
end sub

' The config or discovery arrived (or went): re-pick home's decoder holder.
sub onHomeHasCam()
    if m.route = "home" or m.route = "picker" then syncHomeDecoder()
end sub
sub startKeepAwake()
    if m.keepAwakeOn then return
    m.keepAwakeOn = true
    m.keepAwake.mute = true
    m.keepAwake.control = "play"
    m.keepAwakeWatchdog.control = "start"
end sub

sub stopKeepAwake()
    m.keepAwakeOn = false
    m.keepAwakeWatchdog.control = "stop"
    m.keepAwake.control = "stop"
end sub

' Restart from the top. Playing from a "finished" position is firmware-unreliable
' (some builds no-op, some re-finish in a tight loop), so we stop first to reset
' the position, then play.
sub restartKeepAwake()
    m.keepAwake.control = "stop"
    m.keepAwake.control = "play"
end sub

' Video has no loop field — replay on "finished", but never while the live/grid
' decoder owns the budget.
sub onKeepAwakeState()
    if m.keepAwake.state = "finished" then
        if m.keepAwakeOn and m.route <> "live" and m.route <> "grid" then
            restartKeepAwake()
        end if
    end if
end sub

' Backstop: if the manual loop ever drops (a missed "finished", a firmware quirk),
' re-assert playback within 30 s so the screensaver can't slip back in. Cheap — it
' only acts when the video isn't already playing on a passive route.
sub onKeepAwakeWatchdog()
    if not m.keepAwakeOn then return
    if m.route = "live" or m.route = "grid" then return
    st = m.keepAwake.state
    if st <> "playing" and st <> "buffering" and st <> "prebuffering" then
        restartKeepAwake()
    end if
end sub

' ---------------------------------------------------------------------------
' ECP /input fan-out
sub setHomeCam(cam as string)
    if cam = "default" then cam = ""
    m.home.homeCam = cam
    m.homeCamTimer.control = "stop"
    if cam <> "" then m.homeCamTimer.control = "start"
    hkEvent("home_cam_override", { cam: cam })
end sub

' The revert push never came: give the card back its own camera.
sub onHomeCamTimer()
    if m.home.homeCam <> "" then setHomeCam("default")
end sub

' ---------------------------------------------------------------------------
sub onInputEvent()
    e = m.inputPump.event
    if e = invalid then return
    dispatchEcp(e)
end sub

sub dispatchEcp(e as object)
    ' homeCam= points the home camera card at another stream (HA: front motion ->
    ' front_steps); "default" goes back to the tile's own cam. No route change, and it
    ' can ride along with any other key.
    if e.homeCam <> invalid and e.homeCam <> "" then setHomeCam(e.homeCam)

    ' overlay= is a complete signal (transient chip); no fall-through.
    if e.overlay <> invalid and e.overlay <> "" then
        m.overlays.callFunc("show", e)
        return
    end if

    ' focusModule= — auto-takeover to a module (or camera) on an HA event.
    if e.focusModule <> invalid and e.focusModule <> "" then
        takeoverModule(e.focusModule, e)
        return
    end if

    ' Severity-driven cam swap (door/motion/intruder).
    if e.cam <> invalid and e.cam <> "" then
        sev = e.severity
        if sev = invalid then sev = "normal"
        replay = hkParseInt(e.replay)
        banner = e.banner
        if banner = invalid then banner = ""

        if sev = "low" then
            pipParams = { overlay: "pip", cam: e.cam }
            if e.duration <> invalid then pipParams.duration = e.duration
            m.overlays.callFunc("show", pipParams)
            if banner <> "" then showToast(banner, "low", 3000)
        else
            beginTakeover()
            goLive(e.cam, replay)
            showToast(toastTextFor(sev, banner, e.cam), sev, 0)
        end if
    end if

    if e.mode <> invalid then
        if e.mode = "home" then
            goHome()
        else if e.mode = "grid" then
            enterGrid()
        else if e.mode = "briefing" then
            showToast("Briefing — coming soon", "low", 2500)
        end if
    end if

    if e.lastMotion <> invalid and e.lastMotion <> "" then
        ts = hkParseInt(e.lastMotionAt)
        m.live.motion = { cam: e.lastMotion, ts: ts }
        gm = m.grid.motion
        if gm = invalid then gm = {}
        gm[e.lastMotion] = ts
        m.grid.motion = gm
    end if
end sub

' Auto-takeover: a camera module (or cam=) takes the screen live, then returns home
' after a TTL (unless the user is already on a self-chosen route). Any other module
' only lights its card on the read-only home wall: no drill-down.
sub takeoverModule(id as string, e as object)
    md = moduleById(id)
    cam = e.cam
    if md <> invalid and isCameraModule(md) then
        if cam = invalid or cam = "" then cam = m.lastLiveCam
        beginTakeover()
        goLive(cam, hkParseInt(e.replay))
    else if md <> invalid then
        m.home.attention = id
        hkEvent("module_attention", { id: id })
    else if cam <> invalid and cam <> "" then
        beginTakeover()
        goLive(cam, hkParseInt(e.replay))
    end if
end sub

sub beginTakeover()
    ' Only auto-return home if the takeover interrupted the passive home route
    ' (the picker sits over home).
    if m.route = "home" or m.route = "picker" then
        m.takeoverActive = true
        m.returnHomeTimer.control = "stop"
        m.returnHomeTimer.control = "start"
    else
        m.takeoverActive = false
    end if
end sub

function toastTextFor(severity as string, banner as string, cam as string) as string
    if banner <> "" then return banner
    return HK_CAM_DISPLAY_NAME(cam)
end function

' ---------------------------------------------------------------------------
' Idle / return-home
' ---------------------------------------------------------------------------
sub resetIdle()
    m.idleTimer.control = "stop"
    if m.manualLive and (m.route = "live" or m.route = "grid") then return
    if m.route = "live" or m.route = "module" or m.route = "grid" or m.route = "diag" or m.route = "picker" then
        m.idleTimer.control = "start"
    end if
end sub

sub onIdleTimer()
    if m.route <> "home" then goHome()
end sub

sub onReturnHomeTimer()
    if m.takeoverActive then goHome()
end sub

' MainScene catches keys the focused group didn't consume — Back climbs the route
' tree to home; any bubbled key cancels an in-progress auto-takeover. HomeGroup takes
' no keys: on home, OK opens the camera picker, * / options the diag screen, Back exits.
function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    ' A user keypress that reaches here means they're interacting — drop takeover.
    m.takeoverActive = false
    m.returnHomeTimer.control = "stop"
    resetIdle()
    if key = "back" then
        if m.route = "home" then return false  ' let the OS exit the channel
        goHome()
        return true
    end if
    if key = "OK" and m.route = "home" then
        goPicker()
        return true
    end if
    ' * / options from the passive home route opens the diagnostic/status screen.
    if key = "options" and m.route = "home" then
        goDiag()
        return true
    end if
    return false
end function

' ---------------------------------------------------------------------------
' Cached discovery + config (registry)
' ---------------------------------------------------------------------------
function readCachedStreams() as object
    raw = regRead(HK_REG_KEY_DISCOVERY())
    if raw = "" then return invalid
    return parseJson(raw)
end function

sub writeCachedStreams(streams as object)
    regWrite(HK_REG_KEY_DISCOVERY(), formatJson(streams))
end sub

sub clearCachedStreams()
    regDelete(HK_REG_KEY_DISCOVERY())
end sub

function readCachedConfig() as object
    raw = regRead(HK_REG_KEY_CONFIG())
    if raw = "" then return invalid
    return parseJson(raw)
end function

sub writeCachedConfig(cfg as object)
    regWrite(HK_REG_KEY_CONFIG(), formatJson(hkSlimConfig(cfg)))
end sub

' ---------------------------------------------------------------------------
' Toast helper
' ---------------------------------------------------------------------------
sub showToast(text as string, severity as string, durationMs as integer)
    req = { text: text, severity: severity }
    if durationMs > 0 then req.durationMs = durationMs
    m.toast.request = req
end sub
