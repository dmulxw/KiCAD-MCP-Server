"""Can ROW16/ROW17 be walked down into the strip from their own stub ends?

_row16 goes up from its J1 pad site and _row17 goes up from its, while the two
neighbours that flank them on the pad row -- ROW15 at x=133.25 and ROW18 at
x=134.75 -- go down.  That leaves a 1.5mm corridor between them, and the dump
suggests it survives to about y=245.4 before CSEL2 (x=133.797) and ROW18
(x=134.516) pinch it to a 0.04mm sliver.  Pinching is a claim about keep-out
arithmetic read off a listing; A* is the measurement.  Start on the net's own
copper at its stub end, aim at any legal cell in the strip band, and if it
fails print the closest cell reached -- the blockade is wherever that stops.

If this succeeds the patch is one short track per net and the architecture
survives untouched: four chips in the strip, J6 only, no array surgery.
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
# The grid quantises the route: cells sit on a lattice and a diagonal step is
# only taken when both of its orthogonal neighbours are legal, so a corridor is
# approached from a staircase that needs more room than the corridor really
# has.  A route that fails by a hundredth of a millimetre may be failing on the
# lattice rather than in the copper, so STEP is a knob too -- the honest
# question is what the clearance is in the continuum, and a finer grid is the
# way to ask it.
STEP = float(os.environ.get("TP_STEP", "0.1"))
CLEAR, SAFETY = 0.20, 0.04
# KEEP is the cell-centre-to-obstacle-edge distance a route needs, i.e. CLEAR
# plus the track's own half-width plus a safety margin.  The panel's DRC floor
# is m_MinClearance 0.200, so at KEEP = 0.34 a route is being asked for
# 0.24mm of copper gap -- 0.04mm more than the fab rules require.  That margin
# is the right default for routing, but it is NOT the right instrument for
# asking whether a corridor exists: a corridor that fails 0.34 by a hundredth
# of a millimetre is open, and calling it sealed would justify a patch the
# geometry does not need.  TP_KEEP sweeps it so the margin can be measured
# instead of assumed.
KEEP = float(os.environ.get("TP_KEEP", CLEAR + 0.1 + SAFETY))
PAD_KEEP = KEEP + 0.20
EGK = KEEP + 0.40
VEK = EGK + 0.3

# net -> the point its own copper currently dead-ends at (the removed J1 pad)
PADS = {"ROW16": (133.750, 243.150), "ROW17": (134.250, 243.150)}
Y_GOAL = float(os.environ.get("TP_Y_GOAL", "244.5"))
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

for name, (px, py) in PADS.items():
    items = [t for t in tracks if t.GetNetname() != name]
    items += [p for p in pads if p.GetNetname() != name]
    g = probe.NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
    g.build(items)

    tgt = [t for t in tracks if t.GetNetname() == name]
    tgt += [p for p in pads if p.GetNetname() == name]
    own = replan.cells_of(g, tgt, LAYERS)

    # A start cell only has to be somewhere the new copper can legally join the
    # net.  Restricting it to the old pad site answers "can the fan-out stub be
    # escaped"; allowing the whole net answers "can the strip reach this net at
    # all", which is the question the architecture actually depends on -- the
    # net's trunk is a highway across the board and touching it anywhere is a
    # connection.  Both are run: the pad answer sizes the local patch, the
    # whole-net answer says whether a patch is needed at all.
    wide = bool(os.environ.get("TP_STARTS_ALL"))
    starts = set()
    for lay, i, j in own:
        x, y = g.x0 + i * STEP, g.y0 + j * STEP
        if not g.OK[lay][j, i]:
            continue
        if wide or ((x - px) ** 2 + (y - py) ** 2 <= 0.5 ** 2 and y >= 242.5):
            starts.add((lay, i, j))

    goals = set()
    for lay in LAYERS:
        ok = g.OK[lay]
        xs = g.x0 + np.arange(g.nx) * STEP
        ys = g.y0 + np.arange(g.ny) * STEP
        band = (ys[:, None] >= Y_GOAL) & (xs[None, :] >= px - 6) \
            & (xs[None, :] <= px + 6)
        sel = ok & np.broadcast_to(band, ok.shape)
        jj, ii = np.nonzero(sel)
        for j, i in zip(jj, ii):
            goals.add((lay, i, j))

    print("\n=== %s: from (%.3f, %.3f) down to y >= %.1f ===" % (name, px, py, Y_GOAL))
    print("  start cells %d   goal cells %d" % (len(starts), len(goals)))
    if not starts:
        print("  NO legal start cell on the net's own copper near the pad site")
        continue
    path, crossing, expanded, closest = probe.astar(g, starts, goals, 25.0, False)
    print("  expanded %d" % expanded)
    if path is None:
        # closest is (heuristic_value, (layer, i, j)) -- h is in cell counts
        h, (clay, ci, cj) = closest
        cx, cy = g.x0 + ci * STEP, g.y0 + cj * STEP
        print("  NO PATH -- h=%.1f cells; closest (%.3f, %.3f) on %s, "
              "%.2fmm above the goal band"
              % (h, cx, cy, "F.Cu" if clay == pcbnew.F_Cu else "B.Cu",
                 Y_GOAL - cy))
        continue
    print("  PATH of %d cells:" % len(path))
    prev = None
    for lay, i, j in path:
        x, y = g.x0 + i * STEP, g.y0 + j * STEP
        if prev is None or lay != prev[0] or abs(x - prev[1]) + abs(y - prev[2]) > 0.45:
            print("    %-5s (%8.3f, %8.3f)"
                  % ("F.Cu" if lay == pcbnew.F_Cu else "B.Cu", x, y))
            prev = (lay, x, y)
    lay, i, j = path[-1]
    print("    end -> (%8.3f, %8.3f)" % (g.x0 + i * STEP, g.y0 + j * STEP))

    # The path is legal by construction at whatever keep we asked for -- but
    # the keep is a knob, and the knob is what decided the answer.  What the
    # fab actually enforces is the raw cell-centre-to-copper-edge distance D: a
    # 0.2mm track centred on a cell leaves D - 0.1mm of gap, and the panel's
    # rule is 0.200.  So report the worst cell on the route and who owns it.
    # That single number separates "already routable and the model was being
    # timid" from "genuinely sealed", which is the whole question.
    worst = min(path, key=lambda c: float(g.D[c[0]][c[2], c[1]]))
    d = float(g.D[worst[0]][worst[2], worst[1]])
    wx, wy = g.x0 + worst[1] * STEP, g.y0 + worst[2] * STEP
    no = int(g.OWN[worst[0]][worst[2], worst[1]])
    who = "--"
    if 0 <= no < len(items):
        who = (items[no].GetNetname() or "--")
    print("  TIGHTEST: D=%.3f at (%.3f, %.3f) %s vs '%s' -> copper gap %.3f "
          "(DRC rule 0.200)"
          % (d, wx, wy, "F.Cu" if worst[0] == pcbnew.F_Cu else "B.Cu", who,
             d - 0.1))
