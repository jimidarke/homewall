' ModulePollTask — fetch the sidecar's /api/config (once) + /api/state (each RUN),
' off the render thread. MainScene sets `hubBase` from discovery, fires control="RUN"
' on a Timer, and observes `snapshot` / `config`. Roku pulls compact JSON; the sidecar
' holds the HA subscription (BrightScript WebSocket support is weak).
'
' Both ask for `?layout=<layout>` (the wall's own module set). A sidecar without that
' layout answers 404, which reaches us as no body (GetToString drops 4xx bodies) or
' as {"error": "unknown layout"}: the config then falls back to the default view
' (logged as layout_fallback) and state follows whichever layout the config came from.
' If a layout state fetch fails later, a default-view probe tells "the layout went
' away" (MainScene re-fetches config) from "the sidecar is down" (stay offline).

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
        layout = m.top.layout
        cfg = hkHttpGetJson(hkWithLayout(hkHubConfigUrl(base), layout))
        active = layout
        if layout <> "" and (cfg = invalid or cfg.error <> invalid) then
            err = "no_response"
            if cfg <> invalid then err = cfg.error.toStr()
            hkEvent("layout_fallback", { layout: layout, err: err })
            cfg = hkHttpGetJson(hkHubConfigUrl(base))
            active = ""
        end if
        if cfg <> invalid and cfg.modules <> invalid then
            m.top.activeLayout = active
            m.top.config = cfg
        end if
    end if

    snap = hkHttpGetJsonTimeout(hkWithLayout(hkHubStateUrl(base), m.top.activeLayout), HK_STATE_TIMEOUT_MS())
    failed = (snap = invalid)
    if not failed then failed = (snap.error <> invalid)
    if failed and m.top.activeLayout <> "" then
        plain = hkHttpGetJsonTimeout(hkHubStateUrl(base), HK_STATE_TIMEOUT_MS())
        if plain <> invalid and plain.error = invalid then
            m.top.ok = false
            m.top.snapshot = { err: "unknown_layout" }   ' MainScene re-fetches config
            return
        end if
    end if
    if failed then
        m.top.ok = false
        m.top.snapshot = { err: "state_fetch_failed" }
        return
    end if

    m.top.ok = true
    m.top.snapshot = snap
end sub
