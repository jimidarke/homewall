' ForecastBody — see ForecastBody.xml.

function FC_DAYS() as integer : return 3 : end function
function STRIP_H() as integer : return 140 : end function
function CHART_GAP() as integer : return 12 : end function
function CHART_MIN_H() as integer : return 160 : end function       ' below this, no chart
function CHART_REFRESH_S() as integer : return 300 : end function   ' chart image cache-bust bucket

sub init()
    m.cols = []
    for i = 0 to FC_DAYS() - 1
        g = m.top.createChild("Group")
        c = { group: g }
        c.day = g.createChild("Label")
        c.glyph = hkPoster(g, "", 56, 56)
        c.hi = g.createChild("Label")
        c.lo = g.createChild("Label")
        c.day.horizAlign = "center"
        c.hi.horizAlign = "right"
        c.hi.vertAlign = "bottom"
        c.lo.vertAlign = "bottom"
        m.cols.push(c)
    end for
    m.none = m.top.createChild("Label")
    m.none.text = "No forecast"
    m.none.visible = false

    ' The temperature chart (sidecar PNG, tile.card): two Posters, the new image shown
    ' only once it has loaded, so a refetch never blanks the chart.
    m.charts = []
    for i = 0 to 1
        p = m.top.createChild("Poster")
        p.loadDisplayMode = "scaleToFit"
        p.visible = false
        p.observeField("loadStatus", "onChartLoad")
        m.charts.push(p)
    end for
    m.front = 0
    m.chartUrl = ""
end sub

sub paint()
    f = m.top.fonts
    if f = invalid then return
    bw = m.top.bodyW
    colW = bw \ FC_DAYS()
    chartH = m.top.bodyH - STRIP_H() - CHART_GAP()
    card = ""
    d = m.top.descriptor
    if d <> invalid and d.tile <> invalid then card = hkStrOr(d.tile.card, "")
    withChart = (card <> "" and m.top.hubBase <> "" and chartH >= CHART_MIN_H())
    y0 = (m.top.bodyH - STRIP_H()) \ 2
    if withChart then y0 = 0
    paintChart(withChart, card, bw, chartH)
    days = []
    v = m.top.values
    if v <> invalid and type(v.outlook) = "roArray" then days = v.outlook

    m.none.font = f.detail
    m.none.color = HK_INK_MUTED()
    m.none.visible = (days.count() = 0)

    for i = 0 to FC_DAYS() - 1
        c = m.cols[i]
        c.group.visible = (i < days.count())
        if i < days.count() then
            day = days[i]
            c.group.translation = [i * colW, y0]
            c.day.font = f.detail
            c.day.color = HK_INK_MUTED()
            c.day.text = hkStrOr(day.label, "")
            c.day.width = colW
            c.day.height = 30

            c.glyph.uri = hkGlyphUri(hkGlyphFor(day.glyph, "weather"), 56)
            c.glyph.translation = [(colW - 56) \ 2, 36]
            hkTint(c.glyph, HK_INK())

            c.hi.font = f.fcHi
            c.hi.color = HK_INK()
            c.hi.text = hkStrOr(day.hi, "—")
            c.hi.translation = [0, 98]
            c.hi.width = colW \ 2 - 4
            c.hi.height = 42

            c.lo.font = f.detail
            c.lo.color = HK_INK_MUTED()
            c.lo.text = hkStrOr(day.lo, "")
            c.lo.translation = [colW \ 2 + 4, 98]
            c.lo.height = 38
        end if
    end for
end sub

' Point the hidden Poster at the chart for this 5-minute bucket; onChartLoad swaps it in.
sub paintChart(enabled as boolean, card as string, w as integer, h as integer)
    if not enabled then
        for each p in m.charts
            p.visible = false
            p.uri = ""
        end for
        m.chartUrl = ""
        return
    end if
    bucket = (hkNowSeconds() \ CHART_REFRESH_S()).toStr()
    url = hkWithLayout(hkHubCardUrl(m.top.hubBase, card, w, h, bucket), HK_LAYOUT())
    for each p in m.charts
        p.translation = [0, STRIP_H() + CHART_GAP()]
        p.width = w
        p.height = h
    end for
    if url = m.chartUrl then return
    m.chartUrl = url
    m.charts[1 - m.front].uri = url
end sub

sub onChartLoad(event as object)
    back = m.charts[1 - m.front]
    if not event.getRoSGNode().isSameNode(back) then return
    if back.loadStatus <> "ready" or back.uri = "" then return
    back.visible = true
    m.charts[m.front].visible = false
    m.front = 1 - m.front
end sub
