"""What exactly is still unconnected on the panel, and where.

73 unconnected items is a number; the question is whether they are 73 separate
mistakes or one broken bus, and whether the break is where the 595s now sit or
somewhere else.  So group them by net, print the two endpoints of each break,
and put them next to the 595 pad rows -- if the open ends sit on those pads the
work is a short fan-out from the new parts; if they sit out at the far edge, the
migration cut something that used to run through them.

  python _tp_broken.py
"""
import collections
import json
import math

import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
DRC = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\_drc_tp_now.json"
TO = pcbnew.ToMM

board = pcbnew.LoadBoard(BOARD)
bb = board.GetBoardEdgesBoundingBox()
print("board: (%.1f,%.1f)-(%.1f,%.1f)"
      % (TO(bb.GetLeft()), TO(bb.GetTop()), TO(bb.GetRight()), TO(bb.GetBottom())))

print("\n=== footprints with 8+ pads in the x<105 strip ===")
for f in sorted(board.GetFootprints(), key=lambda f: f.GetPosition().x):
    pads = list(f.Pads())
    if len(pads) < 8:
        continue
    o = f.GetPosition()
    x, y = TO(o.x), TO(o.y)
    if x > 110:
        continue
    xs = [TO(p.GetPosition().x) for p in pads]
    ys = [TO(p.GetPosition().y) for p in pads]
    print("  %-5s %2d pad(s) origin=(%7.3f,%7.3f) pads x %.2f..%.2f y %.2f..%.2f"
          % (f.GetReference(), len(pads), x, y, min(xs), max(xs), min(ys), max(ys)))

segs = []
for t in board.GetTracks():
    a, c = t.GetStart(), t.GetEnd()
    if isinstance(t, pcbnew.PCB_VIA):
        segs.append((t.GetNetname(), TO(a.x), TO(a.y), TO(a.x), TO(a.y),
                     TO(t.GetWidth(pcbnew.F_Cu)) / 2.0, "via"))
    else:
        segs.append((t.GetNetname(), TO(a.x), TO(a.y), TO(c.x), TO(c.y),
                     TO(t.GetWidth()) / 2.0, board.GetLayerName(t.GetLayer())))


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def touching(net, x, y, reach):
    best = None
    for (n, ax, ay, bx, by, hw, what) in segs:
        if n != net:
            continue
        d = seg_dist(x, y, ax, ay, bx, by)
        if d <= hw + reach and (best is None or d < best[0]):
            best = (d, ax, ay, bx, by, what)
    return best


print("\n=== pads whose net has copper, but none of it at the pad ===")
naked = []
for f in board.GetFootprints():
    for p in f.Pads():
        net = p.GetNetname()
        if not net or net == "GND":
            continue
        o = p.GetPosition()
        x, y = TO(o.x), TO(o.y)
        if touching(net, x, y, 0.05) is not None:
            continue
        pb = p.GetBoundingBox()
        reach = max(TO(pb.GetWidth()), TO(pb.GetHeight())) / 2.0 + 0.10
        naked.append((net, f.GetReference(), str(p.GetNumber()), x, y,
                      touching(net, x, y, reach)))

by_net = collections.defaultdict(list)
for (net, ref, num, x, y, near) in naked:
    by_net[net].append((ref, num, x, y, near))
print("%d pad(s) on %d net(s)" % (len(naked), len(by_net)))
for net in sorted(by_net):
    v = by_net[net]
    gone = sum(1 for e in v if e[4] is None)
    print("  %-8s %2d pad(s)%s" % (net, len(v),
                                   "   (net has NO copper anywhere)" if gone == len(v) else ""))
    for (ref, num, x, y, near) in sorted(v, key=lambda e: e[3])[:8]:
        print("      %-5s pad %-3s (%8.3f,%8.3f)  %s"
              % (ref, num, x, y, "--- no copper on this net at all ---" if near is None
                 else "nearest %.2f mm (%s at %.1f,%.1f)"
                 % (near[0], near[5], near[1], near[2])))

print("\n=== DRC unconnected, endpoints ===")
try:
    d = json.load(open(DRC, encoding="utf-8"))
except Exception as e:
    print("  (%s)" % e)
    d = None
if d:
    for i in d["unconnected_items"]:
        a, b = i["items"][0], i["items"][1]
        pa, pb = a["pos"], b["pos"]
        print("  (%8.3f,%8.3f) %-40s <-> (%8.3f,%8.3f) %s"
              % (pa["x"], pa["y"], a["description"][:40],
                 pb["x"], pb["y"], b["description"][:40]))
