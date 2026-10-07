' BackgroundListTask — GET /api/backgrounds, publish the ordered URL list.
' Task-thread only (blocking URL transfer). See BackgroundListTask.xml.

sub init()
    m.top.functionName = "runList"
end sub

sub runList()
    base = m.top.hubBase
    if base = invalid or base = "" then base = hkHubBase()
    if base = invalid or base = "" then
        m.top.result = []
        return
    end if

    data = hkHttpGetJson(hkHubBackgroundsUrl(base))
    urls = []
    if data <> invalid and data.images <> invalid then
        for each img in data.images
            if img <> invalid and img.url <> invalid and img.url <> "" then
                ' Ask the sidecar to pre-size to the panel so we don't hold
                ' oversized bitmaps; the sidecar caches per (name, size, fit). `cover`
                ' fills the screen: most of the shared drone photos are 4:3, which
                ' `contain` would pillarbox in black.
                sep = "?"
                if Instr(1, img.url, "?") > 0 then sep = "&"
                urls.push(img.url + sep + "w=1920&h=1080&fit=cover")
            end if
        end for
    end if
    hkEvent("bg_list", { count: urls.count() })
    m.top.result = urls
end sub
