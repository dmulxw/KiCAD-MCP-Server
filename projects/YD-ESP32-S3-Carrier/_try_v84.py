"""Does another 10 mm of board height let all 31 panel nets route?

_probe_lanes.py measured the wall exactly: in the header field the two 1x20 rows
leave three free bands (2.94 / 1.38 / 0.04 mm at board height 74), and those bands
carry 5+3+1 lanes per layer -- 18 in all, on both layers together.  The router
placed 18 nets.  The count is not a coincidence; it is the band arithmetic.

Free y per layer, L, carries about L / 0.62 lanes, so 31 nets need ~9.6 mm of free
band on each layer, not 4.36.  The pad rows cost a fixed 4.64 mm of the strip
whatever its height, so the board has to grow by roughly what is missing.

This builds a scratch board at y 0..84 and routes the panel nets on it, twice:

  keep  -- J8/J10 stay at 68.1 / 71.8, the whole extra 10 mm lands below J10
  south -- J8/J10 move to 75.0 / 78.6, splitting the extra room above and below

Nothing is written back to the real board; the scratch file is the only output.
"""
import importlib.util
import os
import shutil
import sys

import pcbnew

MODE = sys.argv[1] if len(sys.argv) > 1 else "keep"
SCRATCH = "_v84.kicad_pcb"

spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

H = 84.0
shutil.copyfile(rt.BOARD, SCRATCH)

board = pcbnew.LoadBoard(SCRATCH)
KEEP = []                                    # graveyard: see route.py notes

# Replace the outline with a 0,0-100,H rectangle.
for d in list(board.GetDrawings()):
    if d.GetLayer() == pcbnew.Edge_Cuts:
        board.Remove(d)
        KEEP.append(d)

for (x0, y0, x1, y1) in ((0, 0, 100, 0), (100, 0, 100, H),
                         (100, H, 0, H), (0, H, 0, 0)):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
    s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(pcbnew.FromMM(0.10))
    board.Add(s)

# J8 carries 16 of the 31 nets and its only clean approach is the band above it, so
# the useful question is not "is the board taller" but "how is the free height split
# between the bands".  j8south spends the height on that band; balanced splits it
# evenly between J8's band and J10's.
MOVES = {"keep": {}, "south": {"J8": 75.0, "J10": 78.6},
         "j8south": {"J8": 73.0, "J10": 76.6},
         "balanced": {"J8": 71.5, "J10": 75.16}}[MODE]
for fp in board.GetFootprints():
    if fp.GetReference() in MOVES:
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(2.0),
                                       pcbnew.FromMM(MOVES[fp.GetReference()])))
board.Save(SCRATCH)
print("%s: outline 0,0-%g,%g   headers %s" % (MODE, 100, H, MOVES or "unmoved"))

# Re-point the router at the taller board.
rt.BOARD = SCRATCH
rt.BOARD_H = H
rt.NY = int(H / rt.GRID) + 1

board = pcbnew.LoadBoard(SCRATCH)
R = rt.Router(board)
rt.absorb(board, R)

PANEL = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
# ONLY_SET=ROW1,CSEL3 routes just those, on the bare board.  A net that routes alone
# but not in company is a contention failure -- the ordering is what to fix.  One
# that fails alone as well is still geometric, and the layout is what to fix.
_only = os.environ.get("ONLY_SET")
if _only:
    PANEL = _only.split(",")
todo = [n for n in PANEL if len(R.pads.get(n, [])) >= 2]


def span(n):
    pts = R.pads[n]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5


todo.sort(key=span)

# The initial order is the whole game: the escalating-radius phase reached 4 net
# failures, and every star round after it reached 8.  The star phase is not merely
# a fixed point, it is worse than what precedes it, so what to vary is the order
# the nets are first laid down in.  `hard` puts the four known stragglers first,
# on the reasoning that a net that barely fits should not have to fit around 27
# others.
ORDER = os.environ.get("ORDER", "span")
if ORDER == "rev":
    todo.reverse()
elif ORDER == "hard":
    FIRST = ["ROW1", "CSEL3", "CSEL4", "ROW11"]
    todo = [n for n in FIRST if n in todo] + [n for n in todo if n not in FIRST]
elif ORDER == "x":
    todo.sort(key=lambda n: min(p[0] for p in R.pads[n]))
print("order %s: %s" % (ORDER, " ".join(todo[:6]) + " ..."))

failed = rt.route_all(R, todo, rounds=int(os.environ.get("ROUNDS", 4)))
print("%-5s %2d of %d panel net(s) failed: %s"
      % (MODE, len(failed), len(todo), " ".join(failed) or "-"))
