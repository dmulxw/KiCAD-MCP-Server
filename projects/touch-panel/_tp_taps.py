"""Where the F.Cu GND taps land, so a B.Cu trunk can be put under them.

The falsification test is settled: lifting the 127 F.Cu GND segments from the R
column turns 13 R-column nets from FAIL to OK, and the baseline control is sound
(_base copper == the working board's, 2624 seg / 548 via; _nospine closes exactly,
2624-127+188=2685, 548+24=572).

So the real edit is that removal plus a GND replacement.  This is the measurement
that shapes it.  Two facts drive the design:

  * the R pads are SMD, so B.Cu has no pad conflicts anywhere under the column --
    a B.Cu trunk can run dead centre between pad 1 and pad 2, which F.Cu provably
    cannot (0.48 mm gap vs 0.60 mm needed);
  * the pad-2 taps are 45-degree F.Cu run that END at x 102.610 on pad 2.  They
    are east of the lift box, so they survive it -- but once the weave is gone
    their west ends dangle, and that is exactly where the new feed must attach.

  python _tp_taps.py
"""
from collections import Counter

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X0, X1 = 99.0, 103.6
YLO, YHI = 105.0, 246.0

board = pcbnew.LoadBoard(BOARD)

# ---- 1. the taps: F.Cu GND copper whose metal reaches east of the lift box ---
print("=== F.Cu GND segments reaching east of x=102.45 (the pad-2 taps) ===")
taps = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.F_Cu:
        continue
    if t.GetNetname() != "GND":
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if max(x1, x2) < 102.45 or min(x1, x2) > X1:
        continue
    if max(y1, y2) < YLO or min(y1, y2) > YHI:
        continue
    taps.append((x1, y1, x2, y2, TO(t.GetWidth())))
taps.sort(key=lambda r: min(r[1], r[3]))
for (x1, y1, x2, y2, w) in taps:
    print("   (%8.3f,%8.3f) -> (%8.3f,%8.3f)  L=%5.2f w=%.2f"
          % (x1, y1, x2, y2, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** .5, w))

# ---- 2. all GND vias in the band, to see what already ties F.Cu to B.Cu -----
print("\n=== GND vias in x %.2f..%.2f, y %.2f..%.2f ===" % (X0, X1, YLO, YHI))
gv = []
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        continue
    p = t.GetPosition()
    x, y = TO(p.x), TO(p.y)
    if not (X0 <= x <= X1 and YLO <= y <= YHI):
        continue
    net = str(t.GetNetname())
    if net == "GND":
        gv.append((y, x, TO(t.GetWidth(pcbnew.F_Cu)), TO(t.GetDrillValue())))
for (y, x, w, d) in sorted(gv):
    print("   (%8.3f,%8.3f) pad=%.2f drill=%.2f" % (x, y, w, d))
print("   %d GND via(s) in the band" % len(gv))

# ---- 3. B.Cu occupancy, so the trunk has a known-clear x -------------------
print("\n=== B.Cu copper in x %.2f..%.2f (segments and vias) ===" % (X0, X1))
occ = Counter()
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.B_Cu:
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if max(x1, x2) < X0 or min(x1, x2) > X1:
        continue
    if max(y1, y2) < YLO or min(y1, y2) > YHI:
        continue
    occ[str(t.GetNetname())] += 1
for net, n in occ.most_common():
    print("   %-10s %3d seg(s)" % (net, n))
if not occ:
    print("   (empty)")

# every via, any net, that a B.Cu trunk would have to dodge
print("\n=== vias of any net in the band (a via blocks both layers) ===")
allv = []
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        continue
    p = t.GetPosition()
    x, y = TO(p.x), TO(p.y)
    if not (X0 <= x <= X1 and YLO <= y <= YHI):
        continue
    allv.append((y, x, str(t.GetNetname()), TO(t.GetWidth(pcbnew.F_Cu))))
print("   %d via(s)" % len(allv))
for (y, x, net, w) in sorted(allv)[:80]:
    print("   (%8.3f,%8.3f) %-10s pad=%.2f" % (x, y, net, w))

# ---- 4. for each R row: the free x-window on F.Cu at the pad-2 scanline -----
print("\n=== R pad rows: is the gap between pad1 and pad2 clear on F.Cu? ===")
S = 1e6
rows = {}
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    if not (ref.startswith("R") and ref[1:].isdigit()):
        continue
    ps = {str(p.GetNumber()): p for p in fp.Pads()}
    if "1" not in ps or "2" not in ps:
        continue
    b = ps["1"].GetBoundingBox()
    rows[ref] = ((b.GetLeft() + b.GetRight()) / 2 / S,
                 (b.GetTop() + b.GetBottom()) / 2 / S,
                 ps["1"], ps["2"])
for ref in sorted(rows, key=lambda r: int(r[1:])):
    cx, cy, p1, p2 = rows[ref]
    b1, b2 = p1.GetBoundingBox(), p2.GetBoundingBox()
    e1, s2 = b1.GetRight() / S, b2.GetLeft() / S
    # F.Cu metal crossing the pad-1 scanline in the gap
    blk = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.F_Cu:
            continue
        s, e = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
        w = TO(t.GetWidth())
        if not (min(y1, y2) - w / 2 <= cy <= max(y1, y2) + w / 2):
            continue
        if abs(y1 - y2) < 1e-6:
            xc = (x1 + x2) / 2.0
        else:
            xc = x1 + (cy - y1) / (y2 - y1) * (x2 - x1)
        if xc + w / 2 >= e1 and xc - w / 2 <= s2:
            blk.append(str(t.GetNetname()))
    print("   %-5s y=%7.3f  pad1 edge=%.3f  pad2 edge=%.3f  gap=%.3f  %s"
          % (ref, cy, e1, s2, s2 - e1,
             ("BLOCKED by " + ",".join(sorted(set(blk)))) if blk else "clear"))
