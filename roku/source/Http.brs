' HAku — shared blocking HTTP JSON GET. Task-thread only (blocks the caller).
' The module poll, discovery and any future feed all fetch through these helpers.

function hkHttpGetJson(url as string) as object
    body = hkHttpGetString(url)
    if body = invalid or body = "" then return invalid
    return ParseJson(body)
end function

' The same GET with a deadline: a 2xx body, else invalid on an error status or when
' nothing has come back after timeoutMs (the transfer is cancelled). The 1 s state poll
' uses it so a hung sidecar can't hold the Task for minutes.
function hkHttpGetJsonTimeout(url as string, timeoutMs as integer) as object
    if url = invalid or url = "" then return invalid
    port = createObject("roMessagePort")
    t = createObject("roUrlTransfer")
    t.setUrl(url)
    t.setRequest("GET")
    t.setMessagePort(port)
    t.enableEncodings(true)
    if not t.asyncGetToString() then return invalid
    msg = wait(timeoutMs, port)
    if type(msg) <> "roUrlEvent" then
        t.asyncCancel()
        return invalid
    end if
    code = msg.getResponseCode()
    if code < 200 or code >= 300 then return invalid
    body = msg.getString()
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
