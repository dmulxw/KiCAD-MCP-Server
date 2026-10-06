"""What is CSEL3, and what would it cost to take it out of the west corridor?

_tp_chan.py measured that with CSEL3's copper removed, the west corridor's worst
pinch goes from 3 usable lanes to 4 -- and 4 is exactly what the four 595 control
signals need.  So CSEL3 is the single item standing between the board and a
feasible control bus.

That makes three things worth knowing before touching it:
  * is CSEL3 connected at all (it is a Group B net, i.e. reported unconnected),
  * where does it actually go -- which pads, which end of the board,
  * how much of the corridor does it really occupy, and is there anywhere else
    for it.

  python _tp_csel3.py
"""
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
NET = "CSEL3"

board = pcbnew.LoadBoard(BOARD)

print("=== every pad on %s ===" % NET)
for fp in board.GetFootprints():
    for p in fp.Pads():
        if str(p.GetNetname()) != NET:
            continue
        r = p.GetBoundingBox()
        print("  %-6s pad %-3s  x %.3f..%.3f  y %.3f..%.3f"
              % (str(fp.GetReference()), str(p.GetNumber()),
                 r.GetLeft() / S, r.GetRight() / S,
                 r.GetTop() / S, r.GetBottom() / S))

print("\n=== every track/via on %s ===" % NET)
segs = defaultdict(list)
vias = []
for t in board.GetTracks():
    if str(t.GetNetname()) != NET:
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        d = TO(t.GetWidth(pcbnew.F_Cu))
        dr = TO(t.GetDrillValue())
        vias.append((TO(q.x), TO(q.y), d, dr))
        continue
    s, e = t.GetStart(), t.GetEnd()
    lay = str(t.GetLayerName())
    segs[lay].append((TO(s.x), TO(s.y), TO(e.x), TO(e.y), TO(t.GetWidth())))

for lay in sorted(segs):
    tot = 0.0
    for (x1, y1, x2, y2, w) in segs[lay]:
        tot += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    print("  %-5s %3d segment(s), total %.2f mm, width(s) %s"
          % (lay, len(segs[lay]), tot,
             sorted({round(w, 3) for (_a, _b, _c, _d, w) in segs[lay]})))
for (x, y, d, dr) in vias:
    print("  VIA   at (%.2f, %.2f)  pad %.2f  drill %.2f" % (x, y, d, dr))

print("\n=== the segments that actually enter the corridor (x < 92.5) ===")
for lay in sorted(segs):
    for (x1, y1, x2, y2, w) in sorted(segs[lay], key=lambda q: min(q[1], q[3])):
        if min(x1, x2) - w / 2 >= 92.5:
            continue
        print("  %-5s (%.2f,%.2f)->(%.2f,%.2f)  w%.2f  yspan %6.2f..%-6.2f"
              "  westmost %.3f"
              % (lay, x1, y1, x2, y2, w, min(y1, y2), max(y1, y2),
                 min(x1, x2) - w / 2))

print("\n=== how much corridor does it own? (x 90.45..91.90 per layer) ===")
for lay, tag in (("F.Cu", pcbnew.F_Cu), ("B.Cu", pcbnew.B_Cu)):
    ys = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) or str(t.GetNetname()) != NET:
            continue
        if t.GetLayer() != tag:
            continue
        s, e = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
        w = TO(t.GetWidth()) / 2
        if min(x1, x2) - w < 91.90 and max(y1, y2) > 166 and min(y1, y2) < 246:
            ys.append((min(y1, y2), max(y1, y2)))
    if not ys:
        print("  %-5s none" % lay)
        continue
    ys.sort()
    merged = [list(ys[0])]
    for (a, b) in ys[1:]:
        if a <= merged[-1][1] + 0.01:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    print("  %-5s %d segment(s) span y %s"
          % (lay, len(ys), ", ".join("%.1f-%.1f" % (a, b) for a, b in merged)))

print("\n=== is CSEL3 whole, or in pieces? (endpoints that touch nothing else) ===")
pts = defaultdict(int)
for lay in segs:
    for (x1, y1, x2, y2, _w) in segs[lay]:
        pts[(lay, round(x1, 2), round(y1, 2))] += 1
        pts[(lay, round(x2, 2), round(y2, 2))] += 1
dangling = [k for k, v in pts.items() if v == 1]
print("  %d segment endpoint(s); %d appear only once (candidate dangling ends)"
      % (sum(pts.values()), len(dangling)))
for k in sorted(dangling, key=lambda q: q[2])[:20]:
    print("     %-5s (%.2f, %.2f)" % k)
