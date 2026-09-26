"""How compactly can ROW3/ROW5 get out of J1?

The free-handed A* takes the shortest path it can find, and on a saturated
board that is a long detour: 187mm and 205mm for runs whose trunks are ~115mm
away. Length is not the problem -- the detour eats the space the other nets
needed, and 12 of them then had nowhere to go.

Capping the search to a box forces a compact escape, and the smallest box that
still admits a path is the most compact one. Sweeping the box shows how much
room these two nets really need, which is the number that decides whether the
re-plan is cheap or a full re-route of the bottom of the board.

Only the northern copper counts as a goal here. A net has ~50 pads spread over
the board, so "reached a goal" is not the same as "reached the trunk" -- a
route that stops at a stray pad leaves the net split exactly as before.

    python corridor.py <src> --limits "120 125 145 245;115 125 150 245"
"""
import argparse
import sys
import time

import pcbnew

from replan import Geom, Router

S = 1e6

#: Removed items must outlive the *process*, not just the attempt that dropped
#: them. BOARD::Remove hands the item to Python, and collecting that proxy
#: tears down SWIG's type registry globally -- the next LoadBoard in the same
#: process returns a bare SwigPyObject. One list for the whole run.
GRAVEYARD = []


def attempt(src, ripbox, limit, nets, step, safety, goal_max_y):
    board = pcbnew.LoadBoard(src)
    edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
    x0, y0, x1, y1 = ripbox
    lifted = []
    for t in list(board.GetTracks()):
        g = Geom(t)
        bx0, by0, bx1, by1 = g.bbox()
        if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            continue
        lifted.append(g)
        board.Remove(t)
        GRAVEYARD.append(t)
    r = Router(board, step, safety, 0.2, [pcbnew.F_Cu, pcbnew.B_Cu],
               edge_clear)
    out = []
    for name in nets:
        recs = r.route(name, limit=limit, goal_max_y=goal_max_y)
        ln = sum(x[2] for x in recs)
        nv = sum(x[4] for x in recs)
        out.append((name, ln, nv, bool(recs)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--rip", nargs=4, type=float, default=[128, 241, 174, 246],
                    metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--nets", nargs="+", default=["ROW3", "ROW5"])
    ap.add_argument("--limits", required=True,
                    help="semicolon-separated 'x0 y0 x1 y1' boxes, or '-' for "
                         "an unbounded search")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--safety", type=float, default=0.04)
    ap.add_argument("--goal-max-y", type=float, default=200.0)
    a = ap.parse_args()

    for spec in a.limits.split(";"):
        spec = spec.strip()
        limit = None if spec == "-" else [float(v) for v in spec.split()]
        t = time.time()
        print(f"\n### limit {'unbounded' if limit is None else spec}")
        sys.stdout.flush()
        out = attempt(a.src, a.rip, limit, a.nets, a.step, a.safety,
                      a.goal_max_y)
        for name, ln, nv, ok in out:
            print(f"  {name}: {'OUT ' if ok else 'NO PATH'} "
                  f"{ln:6.1f}mm  {nv} via(s)")
        print(f"  ({time.time()-t:.0f}s)")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
