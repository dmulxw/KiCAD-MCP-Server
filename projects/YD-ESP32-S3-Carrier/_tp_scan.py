"""Which matrix nets can the strip actually reach?  One A* per net.

_tp_cover.py screened this with a clearance-gap proxy and reported the strip
plus its margin still leaving ROW8/ROW16/ROW17/ROW19/ROW20 out -- but the proxy
is a union over positions and a union is not a placement, and this session's
A* has already contradicted it once (it walks ROW16 into the strip at keep
0.30 on a 0.05mm grid, which the proxy called sealed).  So do it the way that
cannot lie: for each net, build the grid with every OTHER net as obstacle, take
every legal cell on the net's own copper as a start, and every legal cell in
the strip band as a goal.  Starts are the whole net, not the J1 pad site,
because the question the architecture depends on is whether the strip can touch
this net anywhere -- the net's trunk is a highway across the board.

Two knobs decide the answer and both are printed, so a verdict can be read as
"legal at the fab rule" or "legal only with the safety margin given up":
TP_KEEP is clearance + track half-width + safety, and STEP is the lattice the
route is quantised to.  A route found only at KEEP 0.30 / STEP 0.05 is a route
with zero engineering margin that the production grid cannot even express.
"""
import os
import sys

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
import replan                                              # noqa: E402
import probe                                               # noqa: E402

S = 1e6
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
STEP = float(os.environ.get("TP_STEP", "0.1"))
CLEAR, SAFETY = 0.20, 0.04
KEEP = float(os.environ.get("TP_KEEP", CLEAR + 0.1 + SAFETY))
PAD_KEEP = KEEP + 0.20
EGK = KEEP + 0.40
VEK = EGK + 0.3
Y_GOAL = float(os.environ.get("TP_Y_GOAL", "244.5"))
BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")

NAMES = sys.argv[1:]
if not NAMES:
    sys.exit("usage: _tp_scan.py NET [NET ...]")

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard(%s) returned None" % BOARD)

keep_alive = []
if os.environ.get("TP_DROP_J1"):
    gone = [f for f in board.GetFootprints() if f.GetReference() == "J1"]
    for f in gone:
        board.Remove(f)
    keep_alive.extend(gone)

EXT = float(os.environ.get("TP_EXTEND_DOWN", "0"))
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

print("STEP=%.3f  KEEP=%.3f (gap %.3f vs DRC rule 0.200)  strip y >= %.1f"
      % (STEP, KEEP, KEEP - 0.1, Y_GOAL))
print("%-8s %8s %10s  %s" % ("net", "starts", "expanded", "verdict"))

summary = []
for name in NAMES:
    items = [t for t in tracks if t.GetNetname() != name]
    items += [p for p in pads if p.GetNetname() != name]
    g = probe.NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
    g.build(items)

    tgt = [t for t in tracks if t.GetNetname() == name]
    tgt += [p for p in pads if p.GetNetname() == name]
    own = replan.cells_of(g, tgt, LAYERS)

    # goals first: a net already living in the strip needs no route at all
    goals = set()
    ys = g.y0 + np.arange(g.ny) * STEP
    band = ys[:, None] >= Y_GOAL
    for lay in LAYERS:
        sel = g.OK[lay] & np.broadcast_to(band, g.OK[lay].shape)
        jj, ii = np.nonzero(sel)
        for j, i in zip(jj, ii):
            goals.add((lay, i, j))

    starts = set()
    for lay, i, j in own:
        if 0 <= j < g.ny and 0 <= i < g.nx and g.OK[lay][j, i]:
            starts.add((lay, i, j))

    if not tgt:
        print("%-8s %8s %10s  no such net on this board" % (name, "-", "-"))
        continue
    if not starts:
        print("%-8s %8s %10s  net has no legal cell at all (fully buried)"
              % (name, len(own), "-"))
        summary.append((name, "buried"))
        continue
    if starts & goals:
        # already in the strip -- and that is the whole answer, but say where
        x, y = g.x0 + sorted(starts & goals)[0][1] * STEP, \
            g.y0 + sorted(starts & goals)[0][2] * STEP
        print("%-8s %8d %10s  ALREADY in the strip (e.g. %.2f, %.2f)"
              % (name, len(starts), "-", x, y))
        summary.append((name, "present"))
        continue

    path, crossing, expanded, closest = probe.astar(g, starts, goals, 25.0, False)
    if path is None:
        h, (clay, ci, cj) = closest
        print("%-8s %8d %10d  NO PATH -- closest (%.3f, %.3f) %s, %.2fmm short"
              % (name, len(starts), expanded, g.x0 + ci * STEP, g.y0 + cj * STEP,
                 "F.Cu" if clay == pcbnew.F_Cu else "B.Cu", Y_GOAL - (g.y0 + cj * STEP)))
        summary.append((name, "sealed"))
        continue

    worst = min(path, key=lambda c: float(g.D[c[0]][c[2], c[1]]))
    d = float(g.D[worst[0]][worst[2], worst[1]])
    wx, wy = g.x0 + worst[1] * STEP, g.y0 + worst[2] * STEP
    no = int(g.OWN[worst[0]][worst[2], worst[1]])
    who = (items[no].GetNetname() or "--") if 0 <= no < len(items) else "--"
    print("%-8s %8d %10d  PATH %d cells; tightest D=%.3f at (%.3f, %.3f) %s vs "
          "'%s' -> gap %.3f"
          % (name, len(starts), expanded, len(path), d, wx, wy,
             "F.Cu" if worst[0] == pcbnew.F_Cu else "B.Cu", who, d - 0.1))
    summary.append((name, "ok" if d - 0.1 >= 0.200 else "tight"))

print("\n--- verdict tally ---")
for name, st in summary:
    print("  %-8s %s" % (name, st))
