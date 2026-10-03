' DiagHealthTask — GET /api/health, publish it for the diagnostic screen.
' Task-thread only (blocking URL transfer). See DiagHealthTask.xml.

sub init()
    m.top.functionName = "runHealth"
end sub

sub runHealth()
    base = m.top.hubBase
    if base = invalid or base = "" then base = hkHubBase()
    if base = invalid or base = "" then
        m.top.result = { reachable: false, base: "" }
        return
    end if

    data = hkHttpGetJson(hkHubHealthUrl(base))
    if data = invalid then
        m.top.result = { reachable: false, base: base }
        return
    end if
    data.reachable = true
    data.base = base
    m.top.result = data
end sub
