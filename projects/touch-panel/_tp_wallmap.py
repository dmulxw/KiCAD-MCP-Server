"""Map the free space between the 595 column and the R-pad column, layer by layer.

The west-wall work keeps coming back to the same question and keeps being answered
by guesswork: how wide is the wall, and how wide is the door at the top of it?  A
router run says only "failed" -- it never says whether the crossing was 1 lane wide
or 20.  That number decides the whole approach: a 1 mm opening is worth moving three
tracks for, a 0.2 mm one is not, and a 15 mm one means the wall was never the
problem at all.

So this prints, on a 1 mm y grid, every x-run wider than a track needs, for x in
90..112.  `#` marks a run too narrow to carry a 0.30 trace, `-` one that fits
exactly one, and a digit one that fits n side by side.

  python _tp_wallmap.py [board.kicad_pcb]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import _tp_route as R

BOARD = sys.argv[1] if len(sys.argv) > 1 else R.BOARD

board = R.pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)

router = R.Router(board)
R.absorb(board, router)

# A net name that owns nothing, so every piece of copper on the board is an
# obstacle.  This is the pessimistic map: real nets get their own copper carved
# out, which only ever opens more space.
HW = 0.15                     # a 0.30 trace, the width nearly every panel net uses
blk, vblk = router.blocked_for("__nothing__", HW)

X0, X1 = 90.0, 112.0
LANE = R.CLEAR + 2 * HW       # what one trace's centreline needs, edge to edge
print("board %s" % BOARD)
print("a 0.30 trace needs a %.3f mm opening; lane pitch %.3f mm\n" % (LANE, LANE))

i0, i1 = R.gi(X0), R.gi(X1)
for layer, name in ((0, "F.Cu"), (1, "B.Cu")):
    print("=== %s   (x %.0f..%.0f, one line per mm of y) ===" % (name, X0, X1))
    for ymm in range(100, 251):
        j = R.gj(ymm)
        if j < 0 or j >= R.NY:
            continue
        row = blk[layer, i0:i1, j]
        # runs of free cells, in mm
        free = ~row
        out, k = [], 0
        while k < len(free):
            if not free[k]:
                k += 1
                continue
            s = k
            while k < len(free) and free[k]:
                k += 1
            w = (k - s) * R.GRID
            x = R.OX + (i0 + s) * R.GRID
            if w >= R.GRID:            # ignore single cells, they are noise here
                out.append((x, w))
        if not out:
            continue
        txt = []
        for (x, w) in out:
            if w < LANE:
                txt.append("%.1f:#" % x)
            else:
                txt.append("%.1f:%.1f" % (x, w))
        print("  y=%3d  %s" % (ymm, "  ".join(txt)))
    print()
