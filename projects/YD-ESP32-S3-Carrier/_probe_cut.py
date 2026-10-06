"""How many traces can actually cross each x?

Raw free-node counts lie on this board: the header and SOIC pad halos chop a
column into slivers, and a sliver one node wide carries no trace.  What carries a
trace is a *contiguous* run of free nodes, and a run of n nodes holds
1 + (n-1)//LANE traces, because the first trace needs one node and each further
one needs a lane's worth of separation from it.

So walk every column, split it into runs of free nodes per layer, add up what the
runs can hold, and print the profile.  The minimum over the strip is the wall --
compare it with the number of nets that must cross there.

The band limit matters: a whole-board column is dominated by the old board, and
the nets do not care about the old board except as somewhere they might go.
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

LANE = 0.62 / rt.GRID                     # nodes between two 0.30 mm traces


def lanes_in(col):
    """Traces that can cross a column whose free-node pattern is `col`."""
    n = 0
    run = 0
    for v in col:
        if v:
            run += 1
        else:
            if run:
                n += 1 + (run - 1) // int(LANE)
            run = 0
    if run:
        n += 1 + (run - 1) // int(LANE)
    return n


def profile(net, lo, hi):
    w = rt.WIDTHS.get(net, rt.DEFAULT_W)
    bm, _vm = R.blocked_for(net, w / 2.0)
    j0, j1 = max(0, rt.gj(lo)), min(rt.NY - 1, rt.gj(hi))
    free = ~bm[:, :, j0:j1 + 1]
    out = np.zeros(rt.NX, dtype=int)
    for i in range(rt.NX):
        for l in range(2):
            out[i] += lanes_in(free[l, i])
    return out


for net in ("ROW2", "ROW10", "CSEL4"):
    p = profile(net, 63.5, 74.0)
    i = int(np.argmin(p[rt.gi(50.0):rt.gi(98.0)])) + rt.gi(50.0)
    print("%-7s strip y63.5-74  min %d lane(s) at x=%.1f mm" % (net, p[i], rt.mx(i)))

p = profile("ROW2", 63.5, 74.0)
print("\nlane profile, strip y 63.5-74, net ROW2 (31 nets must cross x=50..53):")
for i in range(rt.gi(44.0), rt.gi(100.0) + 1, 10):
    print("  x=%5.1f  %2d lane(s)" % (rt.mx(i), p[i]))

p2 = profile("ROW2", 56.0, 74.0)
print("\nwidened to y 56-74 (the old board south of the strip is still board):")
i = int(np.argmin(p2[rt.gi(50.0):rt.gi(98.0)])) + rt.gi(50.0)
print("  min %d lane(s) at x=%.1f mm" % (p2[i], rt.mx(i)))
for i in range(rt.gi(44.0), rt.gi(100.0) + 1, 10):
    print("  x=%5.1f  %2d lane(s)" % (rt.mx(i), p2[i]))
