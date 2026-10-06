"""Exact geometry of the F.Cu GND spine beside the R column, and what is still open.

_tp_rpad.py proved the R pad-1 column is boxed in by F.Cu GND strands sitting in the
0.48 mm gap between pad 1 and pad 2.  Before deciding how to move them I need the
real topology -- that script printed bounding boxes, which cannot tell a 6.4 mm
vertical from a 0.6 mm jog because both print as `x=... y a..b`.

So this prints every GND track whose copper reaches x 99..103.5 with real
start/end points, grouped into the chain they form, plus the full unconnected
list so the failing nets are on the record rather than inferred.

  python _tp_spine2.py [--all]
"""
import sys
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X0, X1 = 99.0, 103.5
YLO, YHI = 105.0, 245.0

board = pcbnew.LoadBoard(BOARD)

segs, vias = [], []
for t in board.GetTracks():
    if t.GetNetname() != "GND":
        continue
    a, b = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    if isinstance(t, pcbnew.PCB_VIA):
        if X0 <= x1 <= X1 and YLO <= y1 <= YHI:
            vias.append((y1, x1, TO(t.GetWidth(pcbnew.F_Cu))))
        continue
    if t.GetLayer() != pcbnew.F_Cu:
        continue
    if max(x1, x2) < X0 or min(x1, x2) > X1:
        continue
    if max(y1, y2) < YLO or min(y1, y2) > YHI:
        continue
    segs.append((x1, y1, x2, y2, TO(t.GetWidth())))

print("=== F.Cu GND track(s) reaching the band: %d ===" % len(segs))
horiz = [s for s in segs if abs(s[1] - s[3]) < 1e-6]
vert = [s for s in segs if abs(s[0] - s[2]) < 1e-6]
print("  %d horizontal, %d vertical, %d other"
      % (len(horiz), len(vert), len(segs) - len(horiz) - len(vert)))

# Vertical runs are the ones that box a pad: they are the only shape that can sit
# in the 0.48 mm gap between pad 1 and pad 2 and still be long enough to seal it.
print("\n  -- vertical runs, x sorted --")
for (x1, y1, x2, y2, w) in sorted(vert, key=lambda s: (round(s[0], 3), s[1])):
    print("     x=%8.3f  y %8.3f .. %8.3f   L=%6.2f  w=%.2f"
          % (x1, min(y1, y2), max(y1, y2), abs(y2 - y1), w))

print("\n  -- horizontal jogs (x range and the y they sit on) --")
byy = defaultdict(list)
for (x1, y1, x2, y2, w) in horiz:
    byy[round(y1, 3)].append((min(x1, x2), max(x1, x2), w))
for y in sorted(byy):
    runs = sorted(byy[y])
    txt = "  ".join("%.3f..%.3f" % (a, b) for a, b, _w in runs)
    print("     y=%8.3f  %s" % (y, txt))

print("\n  -- vias on GND in the band: %d --" % len(vias))
for (y, x, w) in sorted(vias):
    print("     (%8.3f,%8.3f) pad=%.2f" % (x, y, w))

# x histogram of vertical-run copper, to see exactly where the wall's metal is.
print("\n=== vertical-run copper coverage in x (count of runs whose metal spans x) ===")
for k in range(int(X0 * 10), int(X1 * 10) + 1):
    x = k / 10.0
    n = sum(1 for (x1, y1, x2, y2, w) in vert if abs(x - x1) <= w / 2)
    if n:
        print("     x=%6.2f  %2d run(s)" % (x, n))

# ---- what is still open -----------------------------------------------------
print("\n=== unconnected (from the report) ===")
try:
    import json
    d = json.load(open("_tp_drc.json", encoding="utf-8"))
    tally_net = defaultdict(int)
    for u in d.get("unconnected_items", []):
        for i in u.get("items", []):
            desc = i.get("description", "")
            tally_net[desc] += 1
    print("  %d unconnected item(s); by description:" % len(d.get("unconnected_items", [])))
    for k, v in sorted(tally_net.items(), key=lambda kv: -kv[1]):
        print("     %3d  %s" % (v, k))
except Exception as e:
    print("  (no _tp_drc.json: %s)" % e)
