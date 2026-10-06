"""How many of the 31 matrix nets can a 595 standing in the margin actually drive?

_tp_relax.py measured the gap from each net's copper to the chip-reachable free
space and called 19 of them walled.  That number is a lower bound built from the
wrong question: a gap of 0.42mm is a *legal cell* 0.42mm off the copper, and the
last fraction of a millimetre into your own net is legal by definition, so a
small gap does not mean walled.  The honest test is a path.

Model, stated exactly so the answer can be attacked:
  * obstacles = every track and every pad of the board EXCEPT the target net's
    own copper (you may always land on your own net) -- and the 595 itself is
    not on the board, so its body is not an obstacle either;
  * start = the centre cells of the chip's eight output pads (15, 1..7);
  * goal = any legal cell sitting on the target net's copper;
  * one A* per net, conflict=False, so the path is legal copper at every step.

Because the chip body is absent, a "reachable" verdict means the copper can get
from the chip's output row to that net using free space that exists on today's
board.  It does not yet say eight of them fit at once -- that is the next test.
"""
import os
import sys
import time

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
import replan                                              # noqa: E402
import probe                                               # noqa: E402

S = 1e6
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
STEP = 0.1
CLEAR, SAFETY = 0.20, 0.04
KEEP = CLEAR + 0.1 + SAFETY
PAD_KEEP = CLEAR + 0.3 + SAFETY
EGK = 0.50 + CLEAR + SAFETY
VEK = EGK + 0.3

LIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty"
FP = "SOIC-16_3.9x9.9mm_P1.27mm"
OUT_PADS = ["15", "1", "2", "3", "4", "5", "6", "7"]
SIG = ["ROW%d" % k for k in range(21)] + ["CSEL%d" % k for k in range(10)]

CX = float(sys.argv[1])
CY = float(sys.argv[2])
ROT = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
WANT = sys.argv[4:] or SIG

board = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")
if board is None:
    sys.exit("LoadBoard returned None")

fp0 = pcbnew.FootprintLoad(LIB, FP)
fp0.SetPosition(pcbnew.VECTOR2I(int(round(CX * S)), int(round(CY * S))))
fp0.SetOrientationDegrees(ROT)
START = []
for p in fp0.Pads():
    if p.GetNumber() in OUT_PADS:
        c = p.GetPosition()
        START.append((pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)))
print("chip at (%.2f, %.2f) rot %.0f   output pads x %.2f..%.2f  y %.2f..%.2f"
      % (CX, CY, ROT, min(s[0] for s in START), max(s[0] for s in START),
         min(s[1] for s in START), max(s[1] for s in START)))

tracks = list(board.GetTracks())
pads = [p for f in board.GetFootprints() for p in f.Pads()]
print("board items: %d tracks, %d pads" % (len(tracks), len(pads)))

res = {}
for name in WANT:
    t0 = time.time()
    items = [t for t in tracks if t.GetNetname() != name]
    items += [p for p in pads if p.GetNetname() != name]
    g = probe.NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
    g.build(items)
    tb = time.time() - t0
    starts = []
    for x, y in START:
        i, j = g.ij(x, y)
        if 0 <= i < g.nx and 0 <= j < g.ny:
            for lay in LAYERS:
                if g.OK[lay][j, i]:
                    starts.append((lay, i, j))
    tgt = [t for t in tracks if t.GetNetname() == name]
    tgt += [p for p in pads if p.GetNetname() == name]
    goals = {c for c in replan.cells_of(g, tgt, LAYERS) if g.OK[c[0]][c[2], c[1]]}
    t1 = time.time()
    if not starts:
        res[name] = ("no start cell", 0, 0)
    elif not goals:
        res[name] = ("no legal goal (%d on copper)" % len(replan.cells_of(g, tgt, LAYERS)), 0, 0)
    else:
        path, cross, exp, closest = probe.astar(g, starts, goals, 25.0, False)
        if path is None:
            res[name] = ("NO PATH", len(goals), exp)
        else:
            ln = sum(((path[k][1] - path[k - 1][1]) ** 2
                      + (path[k][2] - path[k - 1][2]) ** 2) ** 0.5
                     for k in range(1, len(path))) * STEP
            res[name] = ("%7.1fmm" % ln, len(goals), exp)
    print("  %-6s %-28s goals %5d  expanded %7d   (build %.1fs route %.1fs)"
          % (name, res[name][0], res[name][1], res[name][2], tb, time.time() - t1),
          flush=True)

ok = [n for n in WANT if res[n][0].endswith("mm")]
bad = [n for n in WANT if n not in ok]
print("\n=== chip at (%.2f, %.2f) rot %.0f: %d/%d nets drivable ==="
      % (CX, CY, ROT, len(ok), len(WANT)))
print("drivable : %s" % " ".join(sorted(ok)))
print("NOT      : %s" % " ".join(sorted(bad)))
