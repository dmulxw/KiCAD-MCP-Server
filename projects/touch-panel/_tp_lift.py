"""Lift the F.Cu GND weave out of the R column, on a scratch copy.

The weave is ~150 F.Cu GND segments in x 100.40..102.45, y 105..246.  It is the
only GND feed to the second terminal of all 21 R pads, so it cannot simply be
deleted -- but this script only builds the *test* board, to answer one question:
with the weave gone, can the router close the 22 nets it currently fails on?

If it can, the real edit is this same removal plus a GND replacement on B.Cu;
if it cannot, the weave is not the binding constraint and the plan is wrong.

  python _tp_lift.py <in.kicad_pcb> <out.kicad_pcb> [--keep-taps]

--keep-taps spares the per-row diagonals that end on R pad 2 (x 102.610), which
sit east of pad 1 and so do not obstruct the approach anyway.  Default removes
everything, which is the maximal-opening version of the test.
"""
import sys
from collections import Counter

import pcbnew

args = [a for a in sys.argv[1:] if not a.startswith("--")]
KEEP_TAPS = "--keep-taps" in sys.argv
SRC, DST = args[0], args[1]

X0, X1 = 100.40, 102.45
Y0, Y1 = 105.0, 246.0
TOL = 0.005

board = pcbnew.LoadBoard(SRC)
if board is None:
    sys.exit("LoadBoard returned None for " + SRC)
TO = pcbnew.ToMM

doomed, kept = [], 0
for t in list(board.GetTracks()):
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.F_Cu or t.GetNetname() != "GND":
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    # wholly inside the box -- a segment that only clips the edge is copper
    # reaching in from outside, and must stay
    if min(x1, x2) < X0 - TOL or max(x1, x2) > X1 + TOL:
        continue
    if min(y1, y2) < Y0 - TOL or max(y1, y2) > Y1 + TOL:
        continue
    if KEEP_TAPS and abs(max(x1, x2) - 102.610) < TOL:
        kept += 1
        continue
    doomed.append(t)

frozen = doomed                 # see clear_routing(): must outlive the save
for t in doomed:
    board.Remove(t)
del frozen

print("lifted %d F.Cu GND segment(s)%s from %s"
      % (len(doomed), "" if not KEEP_TAPS else " (%d pad-2 tap(s) kept)" % kept, SRC))

# what still reaches into the column, so the result of the removal is on record
left = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.F_Cu:
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if max(x1, x2) < X0 or min(x1, x2) > X1:
        continue
    if max(y1, y2) < Y0 or min(y1, y2) > Y1:
        continue
    left.append(str(t.GetNetname()))
print("still in the column: %s"
      % (", ".join("%s x%d" % kv for kv in sorted(Counter(left).items())) or "nothing"))

board.Save(DST)
print("saved", DST)
