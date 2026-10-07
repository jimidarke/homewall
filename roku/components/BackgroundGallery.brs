' BackgroundGallery — rotating photo backdrop. See BackgroundGallery.xml.
'
' State machine (m.phase): idle -> loadingOverlay -> fading -> settling -> idle
'   loadingOverlay : bgB.uri set to the next image, waiting on its loadStatus
'                    (loadTimer aborts a slow/failed load so we don't wedge)
'   fading         : crossfade animation running (bgB opacity 0 -> 1)
'   settling       : bgA.uri copied to the new image; bgB (opaque) still masks it
'                    until bgA is ready (or settleTimer expires) so we never flash
'                    the previous frame. Roku's Poster loadStatus is racy, hence the
'                    timer backstops — never trust a synchronous loadStatus read.

function FALLBACK_URI() as string : return "pkg:/images/bg_fallback.jpg" : end function

sub init()
    m.bgA        = m.top.findNode("bgA")
    m.bgB        = m.top.findNode("bgB")
    m.crossfade  = m.top.findNode("crossfade")
    m.rotate     = m.top.findNode("rotateTimer")
    m.settleTimer = m.top.findNode("settleTimer")
    m.loadTimer  = m.top.findNode("loadTimer")

    m.bgB.observeField("loadStatus", "onBgBLoad")
    m.bgA.observeField("loadStatus", "onBgALoad")
    m.crossfade.observeField("state", "onCrossfadeState")
    m.rotate.observeField("fire", "onRotateFire")
    m.settleTimer.observeField("fire", "onSettleTimer")
    m.loadTimer.observeField("fire", "onLoadTimer")

    m.list    = []
    m.idx     = 0        ' index currently shown on bgA
    m.pending = 0        ' index being transitioned to
    m.phase   = "idle"
    m.queued  = invalid  ' a refreshed list waiting for the current transition to settle

    m.crossfade.duration = HK_BG_CROSSFADE_MS() / 1000.0
    m.rotate.duration = HK_BG_ROTATE_MS() / 1000.0

    ' Fallback shows immediately on cold boot, before the list arrives.
    m.bgA.uri = FALLBACK_URI()
    m.bgA.opacity = 1.0
    m.bgB.opacity = 0.0
end sub

' ---------------------------------------------------------------------------
' Inputs
' ---------------------------------------------------------------------------
sub onImages()
    nxt = []
    imgs = m.top.images
    if imgs <> invalid then
        for each u in imgs
            if u <> invalid and u <> "" then nxt.push(u.toStr())
        end for
    end if

    shown = ""
    if m.list.count() > 0 then shown = m.list[m.idx]
    up = hkBgListUpdate(m.list, nxt, shown)
    if up.action = "same" then return
    if up.action = "keep" then
        hkEvent("bg_list_kept", { count: m.list.count() })
        return
    end if
    if up.action = "swap" then
        ' The list is refreshed every few minutes: carry on from the photo on screen,
        ' once any transition in flight has settled (its indexes are the old list's).
        m.queued = { list: nxt, idx: up.idx }
        if m.phase = "idle" then applyQueued()
        return
    end if

    m.list = nxt
    resetTransition()
    m.idx = 0
    m.bgB.opacity = 0.0
    m.bgB.uri = ""

    if m.list.count() = 0 then
        if m.top.active then m.bgA.uri = FALLBACK_URI()
        m.rotate.control = "stop"
        return
    end if

    ' Only decode a full-screen texture while visible; onActive restores bgA when
    ' we return to a passive route, so a list arriving during live/grid stays cheap.
    if m.top.active then
        m.bgA.uri = m.list[0]
        m.bgA.opacity = 1.0
    end if
    hkEvent("bg_images", { count: m.list.count() })
    startRotation()
end sub

' A changed list, taken between transitions: bgA keeps the photo on screen and the
' hidden overlay preloads the new next one.
sub applyQueued()
    q = m.queued
    if q = invalid then return
    m.queued = invalid
    m.list = q.list
    m.idx = q.idx
    hkEvent("bg_images", { count: m.list.count(), refreshed: true })
    m.bgB.opacity = 0.0
    m.bgB.uri = ""
    startRotation()
end sub

sub onIntervalMs()
    dur = m.top.intervalMs
    if dur < HK_BG_ROTATE_MIN_MS() then dur = HK_BG_ROTATE_MIN_MS()
    m.rotate.duration = dur / 1000.0
    startRotation()
end sub

sub onActive()
    if m.top.active then
        m.top.visible = true
        if m.list.count() > 0 then
            m.bgA.uri = m.list[m.idx]
            m.bgA.opacity = 1.0
        else
            m.bgA.uri = FALLBACK_URI()
        end if
        startRotation()
    else
        ' Hidden behind live/grid video — release the two full-screen textures.
        m.rotate.control = "stop"
        resetTransition()
        m.top.visible = false
        m.bgA.uri = ""
        m.bgB.uri = ""
        m.bgB.opacity = 0.0
    end if
end sub

' ---------------------------------------------------------------------------
' Rotation state machine
' ---------------------------------------------------------------------------
sub startRotation()
    if not m.top.active then return
    if m.list.count() < 2 then
        m.rotate.control = "stop"
        return
    end if
    ' Preload the next frame into the hidden overlay so the first tick is instant.
    nxt = hkBgNextIndex(m.idx, m.list.count())
    if m.bgB.uri = "" then m.bgB.uri = m.list[nxt]
    m.rotate.control = "stop"
    m.rotate.control = "start"
end sub

sub resetTransition()
    m.crossfade.control = "stop"
    m.settleTimer.control = "stop"
    m.loadTimer.control = "stop"
    m.phase = "idle"
    applyQueued()
end sub

sub onRotateFire()
    if m.phase <> "idle" then return
    if m.list.count() < 2 then return
    m.pending = hkBgNextIndex(m.idx, m.list.count())
    m.phase = "loadingOverlay"
    m.bgB.opacity = 0.0
    want = m.list[m.pending]
    if m.bgB.uri = want and m.bgB.loadStatus = "ready" then
        startCrossfade()                     ' already preloaded — safe sync check
    else
        m.bgB.uri = want                     ' onBgBLoad fires when decoded
        m.loadTimer.control = "start"        ' ...or loadTimer aborts a stuck load
    end if
end sub

sub onBgBLoad()
    if m.phase = "loadingOverlay" and m.bgB.loadStatus = "ready" then
        m.loadTimer.control = "stop"
        startCrossfade()
    end if
end sub

sub onLoadTimer()
    ' Next image never loaded — abort this tick; the next tick retries.
    if m.phase = "loadingOverlay" then
        m.bgB.opacity = 0.0
        m.phase = "idle"
        applyQueued()
    end if
end sub

sub startCrossfade()
    m.phase = "fading"
    m.crossfade.control = "start"            ' bgB.opacity 0 -> 1 over bgA
end sub

sub onCrossfadeState()
    if m.phase <> "fading" then return
    if m.crossfade.state <> "stopped" then return
    m.phase = "settling"
    m.idx = m.pending
    ' Copy the settled image down to the base; bgB (opaque) still masks it. Do NOT
    ' trust a synchronous loadStatus here — wait for the event or the settleTimer.
    m.bgA.uri = m.list[m.idx]
    m.settleTimer.control = "start"
end sub

sub onBgALoad()
    if m.phase = "settling" and m.bgA.loadStatus = "ready" then finishSettle()
end sub

sub onSettleTimer()
    if m.phase = "settling" then finishSettle()
end sub

sub finishSettle()
    m.settleTimer.control = "stop"
    m.bgB.opacity = 0.0                       ' reveal bgA (now the new image)
    m.phase = "idle"
    if m.queued <> invalid then
        applyQueued()
        return
    end if
    ' Preload the following frame so the next tick can fade instantly.
    if m.list.count() >= 2 then
        m.bgB.uri = m.list[hkBgNextIndex(m.idx, m.list.count())]
    end if
end sub
