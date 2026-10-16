' CameraPicker — see CameraPicker.xml. The list consumes up/down/OK; Back bubbles
' to MainScene.onKeyEvent, which closes the picker.

sub init()
    m.list = m.top.findNode("list")
    m.list.observeField("itemSelected", "onItemSelected")
end sub

sub onCams()
    content = createObject("roSGNode", "ContentNode")
    cams = m.top.cams
    if cams <> invalid then
        for each c in cams
            row = content.createChild("ContentNode")
            row.title = c.name
        end for
    end if
    m.list.content = content
    m.list.jumpToItem = 0
end sub

sub takeFocus()
    m.list.setFocus(true)
end sub

sub onItemSelected()
    cams = m.top.cams
    i = m.list.itemSelected
    if cams = invalid or i < 0 or i >= cams.count() then return
    m.top.selected = cams[i].id
end sub
