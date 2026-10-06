"""Why can the router not reach R7.1 / R8.1?

route.py reports "cannot reach pad (54.75, 20.075)" seven times for IO10 and
(60.0, 20.825) for IO11, even on a pass where those two nets are the *only*
things to route.  That is a geometric wall, not congestion.  This prints the
pad itself, its immediate neighbours, and every copper item near it.

  python _probe_r78.py
"""
import collections
import pcbnew
import sys

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
board = pcbnew.LoadBoard(HERE + r"\YD-ESP32-S3-Carrier.kicad_pcb")
print("board: %d track/via item(s), %d net(s)"
      % (len(list(board.GetTracks())), board.GetNetCount()))

def mm(v):
    return pcbnew.ToMM(v)

# -- every pad of R6..R9 ---------------------------------------------------
targets = {}
print("\n-- R6..R9 --")
for ref in ("R6", "R7", "R8", "R9"):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        print("   %s: NOT ON BOARD" % ref)
        continue
    print("   %s  %s  at (%.2f, %.2f)  layer=%s"
          % (ref, fp.GetFPID().GetLibItemName(),
             mm(fp.GetPosition().x), mm(fp.GetPosition().y),
             pcbnew.LayerName(fp.GetLayer())))
    for p in fp.Pads():
        pos = p.GetPosition()
        x, y = mm(pos.x), mm(pos.y)
        targets.setdefault(ref, []).append((str(p.GetNumber()), x, y))
        print("      pad %-3s (%7.3f, %7.3f)  net=%-8s size=(%.2f x %.2f)  layer=%s  layers=%s"
              % (p.GetNumber(), x, y, p.GetNetname() or "(none)",
                 mm(p.GetSize().x), mm(p.GetSize().y),
                 pcbnew.LayerName(p.GetLayer()),
                 ",".join(pcbnew.LayerName(l) for l in p.GetLayerSet().Seq())))

# -- what sits around R7.1 / R8.1 -----------------------------------------
for ref, pin in (("R7", "1"), ("R8", "1")):
    cand = [t for t in targets.get(ref, []) if t[0] == pin]
    if not cand:
        continue
    _, cx, cy = cand[0]
    print("\n-- within 2.5 mm of %s.%s (%.3f, %.3f) --" % (ref, pin, cx, cy))

    print("   pads:")
    for f in board.GetFootprints():
        for p in f.Pads():
            pos = p.GetPosition()
            x, y = mm(pos.x), mm(pos.y)
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d <= 2.5 and not (f.GetReference() == ref and str(p.GetNumber()) == pin):
                print("      %-6s.%-3s d=%.2f  net=%-8s layer=%s"
                      % (f.GetReference(), p.GetNumber(), d,
                         p.GetNetname() or "(none)", pcbnew.LayerName(p.GetLayer())))

    print("   copper:")
    cnt = collections.Counter()
    for t in board.GetTracks():
        s, e = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
        # distance from (cx,cy) to the segment
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-9:
            d = ((cx - x1) ** 2 + (cy - y1) ** 2) ** 0.5
        else:
            u = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / L2))
            d = ((cx - (x1 + u * dx)) ** 2 + (cy - (y1 + u * dy)) ** 2) ** 0.5
        if d <= 2.5:
            w = t.GetWidth(pcbnew.F_Cu) if isinstance(t, pcbnew.PCB_VIA) else t.GetWidth()
            cnt[(t.GetNetname() or "(none)", pcbnew.LayerName(t.GetLayer()))] += 1
            print("      %-8s %-6s d=%.2f  w=%.2f  (%.2f,%.2f)-(%.2f,%.2f)"
                  % (t.GetNetname() or "(none)", pcbnew.LayerName(t.GetLayer()),
                     d, mm(w), x1, y1, x2, y2))
    print("   summary: %s" % dict(cnt))

# -- zones ----------------------------------------------------------------
print("\n-- zones --")
for z in board.Zones():
    if z.GetIsRuleArea():
        print("   KEEPOUT layer(s)=%s"
              % ",".join(pcbnew.LayerName(l) for l in z.GetLayerSet().Seq()))
