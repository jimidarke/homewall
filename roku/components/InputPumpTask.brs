' InputPumpTask — bridges ECP /input?key=value... into a SceneGraph field.
'
' Roku posts those params as a roInputEvent (info assoc array) on a roInput's
' message port. We block-wait, then mirror the map into m.top.event which
' alwaysNotify=true so duplicate keys/values still fire the observer.

sub init()
    m.top.functionName = "pump"
end sub

sub pump()
    input = createObject("roInput")
    port = createObject("roMessagePort")
    input.setMessagePort(port)

    while true
        msg = wait(0, port)
        if type(msg) = "roInputEvent" then
            info = msg.getInfo()
            if info <> invalid then
                print "[HAku][input] " + formatInfo(info)
                m.top.event = info
            end if
        end if
    end while
end sub

function formatInfo(info as object) as string
    parts = []
    for each k in info
        parts.push(k + "=" + info[k].toStr())
    end for
    return "{" + parts.join(",") + "}"
end function
