"""Is the strip a genuine capacity wall?

Two numbers decide it, and neither is a whole-column node count:

  * supply -- how many traces fit through a vertical cut at x, summed over the
    free y-window.  Only contiguous free runs carry copper (a one-node sliver
    carries nothing), and a run of n nodes carries 1 + (n-1)//LANE traces.
  * demand -- how many nets actually have pads on both sides of that cut, i.e.
    the nets that have no choice but to cross it somewhere.

Demand > supply at every feasible y-window means no router can ever finish, and
the fix is placement, not ordering.  Demand <= supply but the run still fails
means the router is losing copper it should not, and the fix is in the router.

The y-window matters.  A cut can only be used where it is board: y 64..74 is the
new strip, y 56..74 reaches back into the old board's southern band.
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
print("frozen: %d tracks / %d vias" % (len(R.frozen), len(R.frozen_vias)))

LANE = int(0.62 / rt.GRID)                # nodes between two 0.30 mm traces


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


def supply(net, x, lo, hi):
    """Traces that can cross the cut at x within y in [lo, hi], both layers."""
    w = rt.WIDTHS.get(net, rt.DEFAULT_W)
    bm, _ = R.blocked_for(net, w / 2.0)
    j0, j1 = max(0, rt.gj(lo)), min(rt.NY - 1, rt.gj(hi))
    i = rt.gi(x)
    return lanes_in(~bm[0, i, j0:j1 + 1]) + lanes_in(~bm[1, i, j0:j1 + 1])


def demand(x):
    """Nets with a pad on each side of x -- they must cross it somewhere."""
    out = []
    for net, pads in R.pads.items():
        if len(pads) < 2:
            continue
        xs = [p[0] for p in pads]
        if min(xs) < x <= max(xs):
            out.append(net)
    return sorted(out)


CUTS = [50.4, 51.0, 51.9, 52.4, 53.0, 55.0, 57.0, 60.0]
for lo, hi, tag in ((64.0, 74.0, "strip  y64-74"),
                    (56.0, 74.0, "wide   y56-74"),
                    (0.0, 74.0, "board  y0-74")):
    print("\n%s   (supply for a 0.30 mm trace)" % tag)
    for x in CUTS:
        print("   x=%5.1f  supply %3d   demand %3d"
              % (x, supply("ROW2", x, lo, hi), len(demand(x))))

d = demand(51.9)
print("\n%d net(s) cross x=51.9:" % len(d))
print("  " + " ".join(d))
