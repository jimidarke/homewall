' ModulePollTask — fetch the sidecar's /api/config (once) + /api/state (each RUN),
' off the render thread. MainScene sets `hubBase` from discovery, fires control="RUN"
' on a Timer, and observes `snapshot` / `config`. Roku pulls compact JSON; the sidecar
' holds the HA subscription (BrightScript WebSocket support is weak).

sub init()
    m.top.functionName = "runPoll"
end sub

sub runPoll()
    base = m.top.hubBase
    if base = invalid or base = "" then base = hkHubBase()
    if base = invalid or base = "" then
        m.top.ok = false
        m.top.snapshot = { err: "no_hub_base" }
        return
    end if
    hkSetHubBase(base)  ' cache for cold boot

    if m.top.fetchConfig then
        cfg = hkHttpGetJson(hkHubConfigUrl(base))
        if cfg <> invalid and cfg.modules <> invalid then
            m.top.config = cfg
        end if
    end if

    snap = hkHttpGetJson(hkHubStateUrl(base))
    if snap = invalid then
        m.top.ok = false
        m.top.snapshot = { err: "state_fetch_failed" }
        return
    end if

    m.top.ok = true
    m.top.snapshot = snap
end sub
