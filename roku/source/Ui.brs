' HAku — render-thread helpers for the glass home (v0.11). They touch SceneGraph
' nodes, so they live apart from Config.brs's pure, unit-tested helpers.

' Tint a white Poster: blendColor carries the RGB, opacity the colour's alpha byte
' (0xRRGGBBAA), so "0xFAF6EEC7" draws ink at 78% exactly like a Label would.
sub hkTint(p as object, color as string)
    p.blendColor = Left(color, 8) + "FF"
    p.opacity = Val(Right(color, 2), 16) / 255.0
end sub

' Set `text` in the largest of `fonts` (big to small) that fits `maxW`; failing all,
' the smallest with the label clipped to maxW (Label ellipsizes). Returns the width
' the text takes. label.width is left 0 when the text fits, maxW when it was clipped.
function hkFitLabel(label as object, text as string, fonts as object, maxW as integer) as integer
    label.text = text
    for each f in fonts
        label.width = 0
        label.font = f
        w = label.localBoundingRect().width
        if w <= maxW then return w
    end for
    label.width = maxW
    return maxW
end function

' Natural width of `label`'s current text (width 0 = unconstrained).
function hkTextWidth(label as object) as integer
    label.width = 0
    return label.localBoundingRect().width
end function

function hkStrOr(v as dynamic, dflt as string) as string
    if v = invalid then return dflt
    return v.toStr()
end function

function hkLabel(parent as object, font as object, color as string) as object
    l = parent.createChild("Label")
    l.font = font
    l.color = color
    return l
end function

function hkPoster(parent as object, uri as string, w as integer, h as integer) as object
    p = parent.createChild("Poster")
    p.uri = uri
    p.width = w
    p.height = h
    return p
end function

function hkGlyphUri(name as string, px as integer) as string
    if name = "" then return ""
    return "pkg:/images/glyphs/" + px.toStr() + "/" + name + ".png"
end function
