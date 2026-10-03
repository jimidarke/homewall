' JpegPipTask — fetch a JPEG every intervalMs, publish the local path.
'
' Roku's Poster node will refresh when its `uri` field changes. To avoid the
' Poster reading a partially-written file we ping-pong between two slots:
' write to slot B, then publish B as the new frameUri. The Poster swaps to B,
' next tick we write A, etc.

sub init()
    m.top.functionName = "runFetchLoop"
end sub

sub runFetchLoop()
    cam = m.top.cam
    serverBase = m.top.serverBase
    intervalMs = m.top.intervalMs
    if intervalMs <= 0 then intervalMs = HK_OVERLAY_PIP_INTERVAL_MS()
    if serverBase = "" then serverBase = HK_OVERLAY_SNAPSHOT_BASE()
    if cam = "" then
        hkLog("JpegPipTask: no cam, exiting")
        return
    end if

    url = serverBase + "/api/frame.jpeg?src=" + cam
    slotA = "tmp:/pip_" + cam + "_a.jpg"
    slotB = "tmp:/pip_" + cam + "_b.jpg"
    useA = true

    port = createObject("roMessagePort")
    timer = createObject("roTimespan")

    while LCase(m.top.control) <> "stop"
        timer.mark()
        target = slotB
        if useA then target = slotA

        transfer = createObject("roUrlTransfer")
        transfer.setMessagePort(port)
        transfer.setUrl(url)
        transfer.enableEncodings(true)
        transfer.setMinimumTransferRate(1024, 5)

        if transfer.AsyncGetToFile(target) then
            ev = wait(2000, port)
            if ev <> invalid and type(ev) = "roUrlEvent" and ev.GetResponseCode() = 200 then
                ' Cache-bust the Poster: append a counter so the URI string
                ' changes even when the path is unchanged after a swap.
                m.top.frameUri = target + "?t=" + timer.totalMilliseconds().toStr()
                useA = not useA
            else
                transfer.AsyncCancel()
            end if
        end if

        ' Sleep the remainder of the interval (don't compound fetch latency).
        elapsed = timer.totalMilliseconds()
        if elapsed < intervalMs then sleep(intervalMs - elapsed)
    end while
    hkLog("JpegPipTask: stopped (cam=" + cam + ")")
end sub
