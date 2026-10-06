"""Where the GND weave could go, and what each R row's approach looks like.

_tp_spine2.py gave the weave's shape but not the answer to the only question that
matters: is there a lane it can move to?  F.Cu is provably full -- the gap between
R pad 1 (edge 101.86) and R pad 2 (edge 102.34) is 0.48 mm, and a 0.20 track needs
0.30 of centreline offset from each pad, so 0.60 mm of the gap.  Nothing vertical
fits there on F.Cu, which is why the weave has to zigzag west of pad 1 at all.

So this measures the three things the move depends on:

  1. the board edge, so a new east lane has somewhere to sit;
  2. who else owns B.Cu in the band x 101.7..104 (the trunks stop at 101.552);
  3. for each R row, exactly which nets block a straight run in to pad 1 --
     that is the payoff the move is supposed to buy.

  python _tp_spine3.py
"""
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6

Y0, Y1 = 105.0, 246.0
LANE0, LANE1 = 101.70, 104.00
APPR0, APPR1 = 97.60, 101.90      # the corridor a 595 output would use

board = pcbnew.LoadBoard(BOARD)

# ---- board edge ------------------------------------------------------------
ex, ey = [], []
for d in board.GetDrawings():
    if d.GetLayer() != pcbnew.Edge_Cuts:
        continue
    r = d.GetBoundingBox()
    ex += [r.GetLeft() / S, r.GetRight() / S]
    ey += [r.GetTop() / S, r.GetBottom() / S]
print("board outline  x %.3f..%.3f   y %.3f..%.3f" % (min(ex), max(ex), min(ey), max(ey)))

# ---- footprint pad geometry, so the R rows are read off the board ----------
pads = []
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    if not ref.startswith("R") or not ref[1:].isdigit():
        continue
    for p in fp.Pads():
        q = p.GetBoundingBox()
        pads.append((ref, str(p.GetNumber()), str(p.GetNetname()),
                     q.GetLeft() / S, q.GetTop() / S, q.GetRight() / S, q.GetBottom() / S))
pads.sort(key=lambda r: (int(r[0][1:]), r[1]))
rows = defaultdict(dict)
for (ref, num, net, l, t, r, b) in pads:
    rows[ref][num] = (net, l, t, r, b)

print("\n=== R pads (pad 1 = output, pad 2 = GND) ===")
print("  %-5s %-8s %-24s %-8s %-24s" % ("ref", "pad1 x", "pad1 y", "pad2 x", "pad2 y"))
for ref in sorted(rows, key=lambda r: int(r[1:])):
    p1, p2 = rows[ref].get("1"), rows[ref].get("2")
    if not p1 or not p2:
        continue
    print("  %-5s %6.2f..%-6.2f %6.2f..%-6.2f  %6.2f..%-6.2f %6.2f..%-6.2f"
          % (ref, p1[1], p1[3], p1[2], p1[4], p2[1], p2[3], p2[2], p2[4]))

# ---- B.Cu occupancy in the east lane ---------------------------------------
print("\n=== B.Cu copper in the proposed east lane x %.2f..%.2f, y %.2f..%.2f ==="
      % (LANE0, LANE1, Y0, Y1))
lane = []
for t in board.GetTracks():
    net = str(t.GetNetname())
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.B_Cu:
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if max(x1, x2) < LANE0 or min(x1, x2) > LANE1:
        continue
    if max(y1, y2) < Y0 or min(y1, y2) > Y1:
        continue
    lane.append((net, x1, y1, x2, y2, TO(t.GetWidth())))
if not lane:
    print("  (empty -- the lane is free)")
seen = defaultdict(int)
for (net, x1, y1, x2, y2, w) in lane:
    seen[net] += 1
for net, n in sorted(seen.items(), key=lambda kv: -kv[1]):
    print("  %-10s %3d seg(s)" % (net, n))
for (net, x1, y1, x2, y2, w) in sorted(lane, key=lambda r: (r[0], r[2]))[:40]:
    print("     %-10s (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f" % (net, x1, y1, x2, y2, w))

# vias anywhere near the lane -- a via is a through hole, it blocks both layers
print("\n  -- vias with a pad edge reaching x %.2f..%.2f --" % (LANE0, LANE1))
nv = 0
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        continue
    p = t.GetPosition()
    x, y = TO(p.x), TO(p.y)
    w = TO(t.GetWidth(pcbnew.F_Cu))
    if Y0 > y or y > Y1:
        continue
    if x + w / 2 < LANE0 or x - w / 2 > LANE1:
        continue
    nv += 1
    print("     %-10s (%8.3f,%8.3f) pad=%.2f" % (t.GetNetname(), x, y, w))
if not nv:
    print("     (none)")

# ---- what blocks a straight run in to each R pad 1 -------------------------
print("\n=== F.Cu obstacles on the straight approach to R pad 1 (y = pad row) ===")
HALF = 0.10          # everyone on this board is routed at 0.20
for ref in sorted(rows, key=lambda r: int(r[1:])):
    p1 = rows[ref].get("1")
    if not p1:
        continue
    net, l, t, r, b = p1
    y = (t + b) / 2.0
    hits = []
    for tk in board.GetTracks():
        if isinstance(tk, pcbnew.PCB_VIA) or tk.GetLayer() != pcbnew.F_Cu:
            continue
        s, e = tk.GetStart(), tk.GetEnd()
        x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
        w = TO(tk.GetWidth())
        # does the segment's metal reach this scanline, east of the 595 pads?
        ylo, yhi = min(y1, y2) - w / 2, max(y1, y2) + w / 2
        if not (ylo <= y <= yhi):
            continue
        if abs(y1 - y2) < 1e-6:
            xlo, xhi = min(x1, x2), max(x1, x2)
        else:
            f = (y - y1) / (y2 - y1)
            xc = x1 + f * (x2 - x1)
            xlo = xhi = xc
        xlo -= w / 2
        xhi += w / 2
        if xhi < APPR0 or xlo > APPR1:
            continue
        hits.append((str(tk.GetNetname()), xlo, xhi, w))
    # merge by net
    bynet = defaultdict(lambda: [9e9, -9e9, 0])
    for (nm, xlo, xhi, w) in hits:
        bynet[nm][0] = min(bynet[nm][0], xlo)
        bynet[nm][1] = max(bynet[nm][1], xhi)
        bynet[nm][2] += 1
    txt = "  ".join("%s(%.2f..%.2f)" % (nm, v[0], v[1])
                    for nm, v in sorted(bynet.items()))
    print("  %-5s net=%-8s y=%7.2f  %s" % (ref, net, y, txt if txt else "-- clear --"))
