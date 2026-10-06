"""Does C9-C12 sitting at y=63 cost the strip its northern escape?

The strip nets have to get west past the four 595s.  In the strip itself that is
about 23 lanes against 23 nets, which is no slack at all; the only extra room is
the old board immediately north of y=64, which the y56-74 probe measured at
roughly +15 lanes.

C9-C12 sit at y=63, right in that band, at x 57.5 / 69 / 80.5 / 90 -- one cap in
each of the gaps between the four 595s.  So they may be cutting the escape route
into pieces exactly where it is needed.

This moves them clear (y=52) and re-routes ONLY the 31 panel nets, so the delta
against the same run with the caps in place is the answer.  The move is a
routing experiment, not a proposal: nothing is saved.
"""
import importlib.util
import sys

import pcbnew

spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

WHERE = sys.argv[1] if len(sys.argv) > 1 else "stay"
BOARD = pcbnew.LoadBoard(rt.BOARD)

if WHERE != "stay":
    MOVES = {"C9": (57.5, 52.0), "C10": (69.0, 52.0),
             "C11": (80.5, 52.0), "C12": (90.0, 52.0)}
    for fp in BOARD.GetFootprints():
        ref = fp.GetReference()
        if ref in MOVES:
            x, y = MOVES[ref]
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    print("moved C9-C12 to y=52 for this run")

R = rt.Router(BOARD)
rt.absorb(BOARD, R)

PANEL = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
todo = [n for n in PANEL if len(R.pads.get(n, [])) >= 2]
todo.sort(key=lambda n: ((max(p[0] for p in R.pads[n])
                          - min(p[0] for p in R.pads[n])) ** 2
                         + (max(p[1] for p in R.pads[n])
                            - min(p[1] for p in R.pads[n])) ** 2) ** 0.5)

failed = rt.route_all(R, todo)
print("\n%d of %d panel net(s) failed" % (len(failed), len(todo)))
print("  " + " ".join(failed))
