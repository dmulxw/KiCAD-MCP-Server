"""Can the nets that lost their fan-out be re-routed on p3?

Cheap test of the soft (crowding) cost before paying for another full rip:
load the board that already has ROW3/ROW5 routed, and try to reconnect each
net that the restore stage dropped. A net that finds a path here is one the
full run would have found too.
"""
import sys, time, argparse
import pcbnew
from replan import Router
S = 1e6

ap = argparse.ArgumentParser()
ap.add_argument("board")
ap.add_argument("--soft", nargs=2, type=float, default=None)
ap.add_argument("--nets", nargs="+", required=True)
ap.add_argument("--step", type=float, default=0.05)
ap.add_argument("--safety", type=float, default=0.04)
a = ap.parse_args()

board = pcbnew.LoadBoard(a.board)
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
edge = board.GetDesignSettings().m_CopperEdgeClearance / S
r = Router(board, a.step, a.safety, 0.2, layers, edge,
           soft=tuple(a.soft) if a.soft else None)
ok = bad = 0
for name in a.nets:
    t = time.time()
    recs = r.route(name)
    good = any(x[3] for x in recs)
    ok += good
    bad += (not good)
    print(f"    ({time.time()-t:.0f}s)")
    sys.stdout.flush()
print(f"\n{ok} re-routed, {bad} still no path")
