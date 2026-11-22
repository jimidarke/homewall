' DiscoveryTask: SSDP search, then the discovery.json it points at. See DiscoveryTask.xml.

function DISCOVERY_ST() as string : return "urn:haku:service:dashboard:1" : end function
function DISCOVERY_SCHEMA() as integer : return 2 : end function
function DISCOVERY_WAIT_MS() as integer : return 2500 : end function   ' total time to collect replies
function DISCOVERY_FETCH_MS() as integer : return 5000 : end function

sub init()
    m.top.functionName = "discover"
end sub

sub discover()
    print "[HAku][discovery] searching"
    location = ssdpSearch(DISCOVERY_ST(), DISCOVERY_WAIT_MS())
    if location = "" then
        finish({ ok: false, error: "ssdp_no_response" })
        return
    end if
    print "[HAku][discovery] found " + location

    doc = hkHttpGetJsonTimeout(location, DISCOVERY_FETCH_MS())
    if type(doc) <> "roAssociativeArray" then
        finish({ ok: false, error: "discovery_fetch_failed", location: location })
    else if doc.schemaVersion <> DISCOVERY_SCHEMA() then
        finish({ ok: false, error: "schema_mismatch", got: doc.schemaVersion, want: DISCOVERY_SCHEMA() })
    else if type(doc.streams) <> "roAssociativeArray" then
        finish({ ok: false, error: "no_streams_in_payload" })
    else
        finish({
            ok: true
            streams: doc.streams
            host: doc.host
            sidecar: doc.sidecar
            schemaVersion: doc.schemaVersion
            version: doc.version
        })
    end if
end sub

sub finish(result as object)
    m.top.result = result
end sub

' Multicasts one M-SEARCH and returns the LOCATION of the first reply for `st` that
' arrives within waitMs, or "".
function ssdpSearch(st as string, waitMs as integer) as string
    port = createObject("roMessagePort")
    sock = createObject("roDatagramSocket")
    group = createObject("roSocketAddress")
    if sock = invalid or group = invalid then return ""
    group.setAddress("239.255.255.250:1900")
    local = createObject("roSocketAddress")
    local.setAddress("0.0.0.0:0")   ' any interface, an ephemeral port for the replies
    sock.setAddress(local)
    sock.setMessagePort(port)
    sock.setSendToAddress(group)
    sock.setMulticastTTL(4)
    sock.notifyReadable(true)

    eol = chr(13) + chr(10)
    request = "M-SEARCH * HTTP/1.1" + eol
    request = request + "HOST: 239.255.255.250:1900" + eol
    request = request + "MAN: " + chr(34) + "ssdp:discover" + chr(34) + eol
    request = request + "MX: 2" + eol
    request = request + "ST: " + st + eol + eol
    sock.sendStr(request)

    clock = createObject("roTimespan")
    found = ""
    while found = "" and clock.totalMilliseconds() < waitMs
        msg = wait(waitMs - clock.totalMilliseconds(), port)
        if type(msg) = "roSocketEvent" and sock.isReadable() then
            reply = sock.receiveStr(4096)
            if reply <> invalid and Instr(1, reply, st) > 0 then found = ssdpHeader(reply, "location")
        end if
    end while
    sock.close()
    return found
end function

' Value of an HTTP-style header (case-insensitive name) in a raw SSDP reply, or "".
function ssdpHeader(raw as string, name as string) as string
    re = createObject("roRegex", "^" + name + "\s*:\s*(\S+)", "im")
    hit = re.match(raw)
    if hit.count() < 2 then return ""
    return hit[1]
end function
