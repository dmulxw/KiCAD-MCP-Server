"""Which half of the board is carrying the panel nets?

_thirteen of the thirty-one panel nets strand, and the failing pads are always on
U4/U5/U6 -- the chips east of U3.  Every one of them has to get west past U3's
pads, so the question is how much room that westward crossing really has.

Two runs bracket it.  Block the strip and the nets can only use the old board's
southern band; block the old board and they can only use the strip.  The failure
counts say which half holds the capacity, and therefore which half to widen.

The block is appended to router.shapes as one rect on a name no net owns, which
is the same representation blocked_for() already consumes, so the masks are built
by the router's own code rather than by a private copy of its rules.

  strip    -- panel nets confined to y 64..74
  old      -- panel nets confined to y 0..64
  both     -- no synthetic block, for the baseline
"""
import importlib.util
import sys

import pcbnew

spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

MODE = sys.argv[1] if len(sys.argv) > 1 else "both"
BOARD = pcbnew.LoadBoard(rt.BOARD)
R = rt.Router(BOARD)
rt.absorb(BOARD, R)

NOGO = "_experiment_no_go"
if MODE == "strip":
    R.shapes.append((NOGO, "rect", (-5.0, -5.0, 105.0, 63.9), (0, 1)))
elif MODE == "old":
    R.shapes.append((NOGO, "rect", (-5.0, 64.1, 105.0, 80.0), (0, 1)))

PANEL = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
todo = [n for n in PANEL if len(R.pads.get(n, [])) >= 2]


def span(net):
    pts = R.pads[net]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5


todo.sort(key=span)
failed = rt.route_all(R, todo)
print("%-6s %2d of %d panel net(s) failed: %s"
      % (MODE, len(failed), len(todo), " ".join(failed) or "-"))
