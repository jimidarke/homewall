' HAku — the home screen's type: Barlow, bundled in fonts/ (OFL, see
' fonts/OFL-Barlow.txt), the same two faces the tablet ships. Sizes are the
' tablet's dp x ~1.375 for a TV across the room (Font.size is in px).
'
' Font nodes are render-thread objects: HomeGroup builds one set and hands the same
' nodes to every tile (an assocarray field keeps node references), so a screen of
' cards shares a dozen Font nodes instead of each card making its own.

function hkFontSet() as object
    med = "pkg:/fonts/barlow_medium.ttf"
    semi = "pkg:/fonts/barlow_semi_condensed_semibold.ttf"
    return {
        clock:       hkFont(semi, 56)
        date:        hkFont(med, 28)
        title:       hkFont(med, 24)    ' card title, status word
        hero:        hkFont(semi, 64)
        hero2:       hkFont(semi, 54)   ' hero, stepped down to fit
        hero3:       hkFont(semi, 46)
        sub:         hkFont(med, 28)
        detail:      hkFont(med, 24)    ' detail line, door age, agenda meta, times
        state:       hkFont(semi, 36)   ' door state word
        status:      hkFont(semi, 28)   ' laundry status, stepped down to fit
        status2:     hkFont(semi, 24)
        status3:     hkFont(semi, 20)
        agendaTitle: hkFont(med, 26)
        fcHi:        hkFont(semi, 32)
    }
end function

function hkFont(uri as string, size as integer) as object
    f = CreateObject("roSGNode", "Font")
    f.uri = uri
    f.size = size
    return f
end function
