' HAku — sidecar (hub) URL builders.
'
' The hub base ("http://<host>:1986") is learned from discovery.json's `sidecar`
' block and cached in the registry so a cold boot can poll before SSDP completes.
' An ECP deep-link ?hubBase=... may override it on-device without a rebuild.

' Cached/overridden hub base, or "" if not yet known.
function hkHubBase() as string
    return regRead(HK_REG_KEY_HUB_BASE())
end function

function hkSetHubBase(base as string) as void
    if base <> invalid and base <> "" then regWrite(HK_REG_KEY_HUB_BASE(), base)
end function

function hkHubConfigUrl(base as string) as string
    return hkJoin(base, "/api/config")
end function

function hkHubStateUrl(base as string) as string
    return hkJoin(base, "/api/state")
end function

' Sidecar background gallery list (returns { images: [{ name, url }] }).
function hkHubBackgroundsUrl(base as string) as string
    return hkJoin(base, "/api/backgrounds")
end function

' Sidecar liveness + HA connection status (used by the diagnostic screen).
function hkHubHealthUrl(base as string) as string
    return hkJoin(base, "/api/health")
end function

function hkHubModuleUrl(base as string, moduleId as string) as string
    return hkJoin(base, "/api/module/" + moduleId)
end function

' A rendered PNG card. `path` is the descriptor's drill/tile card path
' ("/api/card/weather_forecast.png"); `v` is a cache-buster (the /api/state ts)
' that forces the Poster to re-fetch at this stable URL — the render cache ignores it.
function hkHubCardUrl(base as string, path as string, w as integer, h as integer, v as string) as string
    if path = invalid or path = "" then return ""
    sep = "?"
    if Instr(1, path, "?") > 0 then sep = "&"
    return hkJoin(base, path) + sep + "w=" + w.toStr() + "&h=" + h.toStr() + "&v=" + v
end function

' A module's home-tile accent icon. `v` here is a sidecar-computed BUCKET
' (weather condition string, or a 5%-stepped fill percentage), not a poll
' timestamp — so the URL, and therefore the Poster, only changes when the
' icon would actually look different (see icons.py::fill_bucket_pct).
function hkHubIconUrl(base as string, moduleId as string, v as string, w as integer, h as integer) as string
    if moduleId = invalid or moduleId = "" then return ""
    if v = invalid then v = ""
    return hkJoin(base, "/api/icon/" + moduleId + ".png") + "?w=" + w.toStr() + "&h=" + h.toStr() + "&v=" + v
end function

' Join a base and a root-relative path, tolerating a trailing slash on base.
function hkJoin(base as string, path as string) as string
    if base = invalid then base = ""
    if Len(base) > 0 and Right(base, 1) = "/" then base = Left(base, Len(base) - 1)
    return base + path
end function
