' HAku — entry point.
'
' Roku's Main(args) receives a deep-link arg map for both cold launches
' (?contentId=...&foo=bar) and hot input pushes (when supports_input_launch=1
' the channel stays alive and Main is re-invoked).

sub Main(args as dynamic)
    screen = createObject("roSGScreen")
    port = createObject("roMessagePort")
    screen.setMessagePort(port)
    scene = screen.createScene("MainScene")
    screen.show()

    ' Hand the deep-link args to the scene. Use an empty assoc array if none.
    if args = invalid or type(args) <> "roAssociativeArray" then
        scene.args = {}
    else
        scene.args = args
    end if
    hkEvent("launch", { args: hkScrub(formatArgs(args)) })

    while true
        msg = wait(0, port)
        if type(msg) = "roSGScreenEvent" then
            if msg.isScreenClosed() then return
        end if
    end while
end sub

function formatArgs(args as dynamic) as string
    if args = invalid or type(args) <> "roAssociativeArray" then return "{}"
    parts = []
    for each k in args
        parts.push(k + "=" + args[k].toStr())
    end for
    return "{" + parts.join(",") + "}"
end function
