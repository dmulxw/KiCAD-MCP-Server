"""How many east-west traces does the strip actually hold, and where do they sit?

The bracketing run settled that the strip is a wall and the old board barely helps
(15/31 alone, 18/31 with the whole board).  What it did not say is *why*, and the
answer decides the fix: if the lanes are missing because the two header rows eat
the strip, the headers have to move or the board has to grow; if they are missing
because the 595s' pads cover the bands on F.Cu, the chips have to move.

So walk the columns from the header field east into the chip field and, for each,
count the contiguous free runs on each layer inside the y bands that matter:
above J8, between the rows, below J10, and the whole strip.  A run of n nodes
carries 1 + (n-1)//LANE traces, the same arithmetic _probe_cut2.py uses.

Chip pads are SMD, so they block F.Cu only -- the per-layer split is the whole
point of printing both.
"""
import importlib.util

import numpy as np
import pcbnew

spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

BOARD = pcbnew.LoadBoard(rt.BOARD)
R = rt.Router(BOARD)
rt.absorb(BOARD, R)
print("frozen: %d tracks / %d vias\n" % (len(R.frozen), len(R.frozen_vias)))

LANE = int(0.62 / rt.GRID)


def lanes_in(col):
    n = run = 0
    for v in col:
        if v:
            run += 1
        else:
            if run:
                n += 1 + (run - 1) // LANE
            run = 0
    return n + (1 + (run - 1) // LANE if run else 0)


bm, _ = R.blocked_for("ROW2", rt.DEFAULT_W / 2.0)
free = ~bm                                   # [layer, i, j]

BANDS = [("above J8  y64.0-66.9", 64.0, 66.9),
         ("between   y69.3-70.6", 69.3, 70.6),
         ("below J10 y73.0-74.0", 73.0, 74.0),
         ("strip     y64.0-74.0", 64.0, 74.0)]

print("%-6s %s" % ("x", "  ".join("%-22s" % b[0] for b in BANDS)))
for x in (2.0, 10.0, 20.0, 30.0, 40.0, 48.0, 50.5, 51.5, 52.5, 55.0,
          57.5, 60.0, 63.0, 69.0, 75.0, 82.0, 90.0, 96.0):
    i = rt.gi(x)
    cells = []
    for (_, lo, hi) in BANDS:
        j0, j1 = max(0, rt.gj(lo)), min(rt.NY - 1, rt.gj(hi))
        f = lanes_in(free[0, i, j0:j1 + 1])
        b = lanes_in(free[1, i, j0:j1 + 1])
        cells.append("F%2d B%2d = %2d" % (f, b, f + b))
    print("%-6.1f %s" % (x, "  ".join("%-22s" % c for c in cells)))
