"""Why is the ground pour absent from the gaps that would join the island up?

The map shows bare board between the three traces that fence the stranded
island off, and those gaps are 1.5-2 mm wide -- far wider than the fill needs.
Either the filler declined to pour there (a rule area, or a width limit), or it
poured and the pour was then removed.  Both are visible from the zone's own
settings plus the keepout list, so print those and ask the polygons directly.

  python _probe_fill.py
"""
import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
TO = pcbnew.ToMM
F_CU, B_CU = pcbnew.F_Cu, pcbnew.B_Cu

board = pcbnew.LoadBoard(BOARD)

print("=== zones ===")
for i, z in enumerate(board.Zones()):
    bb = z.GetBoundingBox()
    print("[%d] net=%-6s ruleArea=%-5s layers=%s  bbox=(%.1f,%.1f)-(%.1f,%.1f)"
          % (i, z.GetNetname(), z.GetIsRuleArea(),
             ",".join(board.GetLayerName(l) for l in (F_CU, B_CU) if z.IsOnLayer(l)),
             TO(bb.GetLeft()), TO(bb.GetTop()), TO(bb.GetRight()), TO(bb.GetBottom())))
    try:
        print("      min_thickness=%.3f clearance=%.3f min_island=%.2f removal=%s"
              % (TO(z.GetMinThickness()), TO(z.GetClearance()),
                 z.GetMinIslandArea() / 1e12, z.GetIslandRemovalMode()))
    except Exception as e:
        print("      (settings unreadable: %s)" % e)
    for l in (F_CU, B_CU):
        if not z.IsOnLayer(l):
            continue
        poly = z.GetFilledPolysList(l)
        print("      %s: %d outline(s) filled" % (board.GetLayerName(l), poly.OutlineCount()))

print("\n=== what sits at the sample points, on F.Cu ===")
pts = [(38.50, 19.50), (38.50, 21.50), (38.50, 22.50),
       (41.00, 21.00), (41.00, 23.00), (43.50, 22.00)]

for (x, y) in pts:
    v = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
    hits = []
    for i, z in enumerate(board.Zones()):
        if not z.IsOnLayer(F_CU):
            continue
        poly = z.GetFilledPolysList(F_CU)
        for k in range(poly.OutlineCount()):
            ch = poly.Outline(k)
            if poly.Contains(v) and ch.PointInside(v):
                hits.append("%s[%d].outline%d" % (z.GetNetname(), i, k))
    near = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != F_CU:
            continue
        a, c = t.GetStart(), t.GetEnd()
        for (px, py, qx, qy) in ((TO(a.x), TO(a.y), TO(c.x), TO(c.y)),):
            dx, dy = qx - px, qy - py
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 <= 1e-12 else max(0.0, min(1.0, ((x - px) * dx + (y - py) * dy) / L2))
            d = ((x - (px + u * dx)) ** 2 + (y - (py + u * dy)) ** 2) ** 0.5
            if d < 1.2:
                near.append("%s d=%.2f w=%.2f" % (t.GetNetname(), d, TO(t.GetWidth())))
    print("  (%.2f,%.2f) zone=%s   tracks<1.2mm: %s"
          % (x, y, ",".join(hits) or "NONE", "; ".join(near) or "none"))
