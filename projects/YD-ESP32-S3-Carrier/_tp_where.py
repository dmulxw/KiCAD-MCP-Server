"""Where does each panel net's copper actually sit in the two margins?

_tp_margins.py answered "which nets have copper in a margin" with total length,
but length is not location: ROW6 has 235.8 mm in the right margin and that could
be one 235 mm run at y=110 or a scribble at y=228.  A 595 output can only join
its net where the net physically is, so before any routing experiment the useful
question is the y-extent of each net's copper in each strip.

Print, per net, the min/max y of its copper with a midpoint inside the strip, and
the same for the strip's free-rectangle bands so the two can be lined up by eye.
"""
import collections

import numpy as np
import pcbnew

b = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")

S = 1e6
STRIPS = (("left ", 90.0, 104.2), ("right", 166.8, 181.0))

pts = collections.defaultdict(list)
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    mx = (s.x + e.x) / 2.0 / S
    my = (s.y + e.y) / 2.0 / S
    pts[n].append((mx, my, pcbnew.ToMM(t.GetLength()), b.GetLayerName(t.GetLayer())))
for fp in b.GetFootprints():
    for p in fp.Pads():
        pos = p.GetPosition()
        pts[p.GetNetname()].append((pos.x / S, pos.y / S, 0.0, "pad"))

NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]

for label, lo, hi in STRIPS:
    print("=== %s margin  x %.1f..%.1f ===" % (label, lo, hi))
    rows = []
    for n in NAMES:
        inside = [(x, y, L, lay) for (x, y, L, lay) in pts.get(n, [])
                  if lo <= x <= hi]
        if not inside:
            rows.append((n, None, None, 0.0, set()))
            continue
        ys = [y for (_, y, _, _) in inside]
        L = sum(t[2] for t in inside)
        lays = {t[3] for t in inside}
        rows.append((n, min(ys), max(ys), L, lays))
    for (n, y0, y1, L, lays) in rows:
        if y0 is None:
            print("  %-6s   --" % n)
        else:
            print("  %-6s  y %7.2f .. %7.2f   %6.1f mm  %s"
                  % (n, y0, y1, L, "".join(sorted(x[0] for x in lays))))
    print()

# Also: how far is each net's nearest copper from a few candidate chip columns?
print("=== nearest copper, by candidate chip column ===")
COL = {"left  x= 92": 92.0, "left  x= 97": 97.0, "left  x=102": 102.0,
       "right x=170": 170.0, "right x=175": 175.0, "right x=179": 179.0}
for label, cx in COL.items():
    line = []
    for n in NAMES:
        best = None
        for (x, y, L, lay) in pts.get(n, []):
            d = ((x - cx) ** 2 + (y - 175.0) ** 2) ** 0.5   # from board mid-height
            if best is None or d < best:
                best = d
        line.append((n, best))
    det = " ".join("%s:%s" % (n, "%.0f" % d if d is not None else "-")
                   for n, d in line)
    print("%s (vs y=175)\n    %s" % (label, det))
