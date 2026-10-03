' HAku — shared blocking HTTP JSON GET. Task-thread only (blocks the caller).
' Mirrors DiscoveryTask.fetchDiscoveryJson / sallynet Http.brs so the module poll,
' discovery, and any future feed all fetch the same tested way.

function hkHttpGetJson(url as string) as object
    body = hkHttpGetString(url)
    if body = invalid or body = "" then return invalid
    return ParseJson(body)
end function

function hkHttpGetString(url as string) as dynamic
    if url = invalid or url = "" then return invalid
    t = createObject("roUrlTransfer")
    t.setUrl(url)
    t.setRequest("GET")
    t.setMessagePort(createObject("roMessagePort"))
    t.enableEncodings(true)
    ' LAN-only http; if the sidecar ever moves to https, cert setup goes here.
    body = t.getToString()
    if body = invalid or body = "" then return invalid
    return body
end function
