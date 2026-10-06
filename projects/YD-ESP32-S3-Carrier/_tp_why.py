"""For one net: where does its reachable free space actually end?

ROW16 and ROW17 came out isolated from the strip *and* from the margins -- the
only two nets for which no chip position anywhere can work.  Isolation is a
strong claim, so it deserves a look at the geometry rather than just a verdict.
This prints, for the named nets, the legal cells on their own copper (the cells
a new track would have to land on), the component those cells belong to per
layer with its bounding box, and how far the strip band is from the nearest
goal cell.  A y-span that stops at 243.15 would say the answer turns on where
the strip band begins rather than on anything physical.
"""
import os
import sys

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
import replan                                              # noqa: E402
import probe                                               # noqa: E402
from _tp_label import label_free                           # noqa: E402

S = 1e6
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
STEP = 0.1
CLEAR, SAFETY = 0.20, 0.04
KEEP = CLEAR + 0.1 + SAFETY
PAD_KEEP = CLEAR + 0.3 + SAFETY
EGK = 0.50 + CLEAR + SAFETY
VEK = EGK + 0.3

NAMES = sys.argv[1:] or ["ROW16", "ROW17"]
EXT = float(os.environ.get("TP_EXTEND_DOWN", "0"))
BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard(%s) returned None" % BOARD)

keep_alive = []
if os.environ.get("TP_DROP_J1"):
    gone = [f for f in board.GetFootprints() if f.GetReference() == "J1"]
    for f in gone:
        board.Remove(f)
    keep_alive.extend(gone)
    print("dropped %d footprint(s): J1" % len(gone))

if EXT:
    ys = [pt.y for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts
          for pt in (d.GetStart(), d.GetEnd())]
    YMAX = max(ys)
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        a, b2 = d.GetStart(), d.GetEnd()
        if abs(a.y - b2.y) < 1:
            continue
        for pt in (a, b2):
            if abs(pt.y - YMAX) < 1:
                pt.y = int(round(pt.y + EXT * S))
        d.SetStart(a)
        d.SetEnd(b2)

tracks = list(board.GetTracks())
pads = [p for f in board.GetFootprints() for p in f.Pads()]

for name in NAMES:
    items = [t for t in tracks if t.GetNetname() != name]
    items += [p for p in pads if p.GetNetname() != name]
    g = probe.NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
    g.build(items)
    comp, K = label_free(g.OK, g.VOK, LAYERS, g.nx, g.ny, quiet=True)

    tgt = [t for t in tracks if t.GetNetname() == name]
    tgt += [p for p in pads if p.GetNetname() == name]
    copper = replan.cells_of(g, tgt, LAYERS)
    goals = [c for c in copper if g.OK[c[0]][c[2], c[1]]]

    print("\n=== %s ===" % name)
    print("  copper cells %d, legal (usable as a goal) %d"
          % (len(copper), len(goals)))
    if copper:
        cj = [c[2] for c in copper]
        print("  copper y span  %.2f .. %.2f"
              % (g.y0 + min(cj) * STEP, g.y0 + max(cj) * STEP))
    if goals:
        gj = [c[2] for c in goals]
        print("  legal-goal y   %.2f .. %.2f   (x %.2f .. %.2f)"
              % (g.y0 + min(gj) * STEP, g.y0 + max(gj) * STEP,
                 g.x0 + min(c[1] for c in goals) * STEP,
                 g.x0 + max(c[1] for c in goals) * STEP))

    lab = {}
    for lay, i, j in goals:
        lab.setdefault(comp[lay][j, i], set()).add(lay)
    for k in sorted(lab, key=lambda k: -len(lab[k])):
        for lay in sorted(lab[k]):
            idx = np.argwhere(comp[lay] == k)
            if not len(idx):
                print("  component #%d absent on %s" % (k, lay))
                continue
            j0, i0 = idx.min(0)
            j1, i1 = idx.max(0)
            print("  component #%-5d on %-4s %8d cells  x %7.2f..%7.2f  y %7.2f..%7.2f"
                  % (k, "F.Cu" if lay == pcbnew.F_Cu else "B.Cu", len(idx),
                     g.x0 + i0 * STEP, g.x0 + i1 * STEP,
                     g.y0 + j0 * STEP, g.y0 + j1 * STEP))
    print("  components in all: %d" % K)
