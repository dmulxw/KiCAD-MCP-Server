"""Find GND pour islands that no via, pad or track touches.

The pour closed 67 GND gaps and left three.  Each remaining unconnected entry
names two F.Cu zone fills, which is what an isolated island looks like from
DRC's side: a separate outline in the filled polygon set that carries no
stitching via to reach the B.Cu plane.

An island is reachable only through a GND item sitting inside it -- a via, a
pad, or a track.  This walks every zone outline and reports the ones with
nothing inside, with their area and the first interior point found, which is
where a stitching via would have to go.

  python _car_islands.py
"""
import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
TO = pcbnew.ToMM

board = pcbnew.LoadBoard(BOARD)

pts = []
for t in board.GetTracks():
    if t.GetNetname() != "GND":
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        pts.append((TO(s.x), TO(s.y), "via"))
    else:
        for e in (t.GetStart(), t.GetEnd()):
            pts.append((TO(e.x), TO(e.y), "track"))
for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNetname() == "GND":
            o = p.GetPosition()
            pts.append((TO(o.x), TO(o.y), "pad %s.%s" % (f.GetReference(), p.GetNumber())))

MODES = {0: "always", 1: "never", 2: "area"}
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    try:
        mode = MODES.get(z.GetIslandRemovalMode(), z.GetIslandRemovalMode())
    except Exception:
        mode = "?"
    print("zone net=%-4s island_removal=%s min_island_area=%.2f mm2  layers=%s"
          % (z.GetNetname(), mode, TO(TO(z.GetMinIslandArea())), 
             [pcbnew.LayerName(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu) if z.IsOnLayer(l)]))
    for layer, lname in ((pcbnew.F_Cu, "F.Cu"), (pcbnew.B_Cu, "B.Cu")):
        if not z.IsOnLayer(layer):
            continue
        poly = z.GetFilledPolysList(layer)
        n = poly.OutlineCount()
        print("   %s: %d island(s)" % (lname, n))
        for i in range(n):
            chain = poly.Outline(i)
            bb = chain.BBox()
            inside = None
            for k in range(0, max(1, chain.PointCount()), max(1, chain.PointCount() // 8)):
                p = chain.CPoint(k)
                c = pcbnew.VECTOR2I((bb.GetLeft() + bb.GetRight()) // 2,
                                    (bb.GetTop() + bb.GetBottom()) // 2)
                if poly.Contains(c):
                    inside = (TO(c.x), TO(c.y))
                    break
            if inside is None:
                for k in range(max(1, chain.PointCount())):
                    c = chain.CPoint(k)
                    if poly.Contains(c):
                        inside = (TO(c.x), TO(c.y))
                        break
            area = abs(chain.Area()) / 1e12
            hits = []
            if inside:
                for (x, y, what) in pts:
                    if abs(x - inside[0]) < 0.001 and abs(y - inside[1]) < 0.001:
                        continue
                    v = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
                    if poly.Contains(v) and chain.PointInside(v):
                        hits.append("(%7.2f,%7.2f) %s" % (x, y, what))
            flag = "OK " if hits else "FLT"
            print("      [%2d] %s area=%7.3f mm2 bbox=(%.2f,%.2f)-(%.2f,%.2f) inside=%s hits=%d"
                  % (i, flag, area, TO(bb.GetLeft()), TO(bb.GetTop()),
                     TO(bb.GetRight()), TO(bb.GetBottom()),
                     ("(%.2f,%.2f)" % inside) if inside else "?", len(hits)))
            for h in hits[:3]:
                print("             ", h)
