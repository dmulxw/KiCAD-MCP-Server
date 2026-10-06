"""Watch route_net() run, rather than re-deriving what it should do.

The single-net test reports `cannot reach pad (124.96, 110.05)` nine times, but
reproducing route_net()'s setup by hand shows A* *can* reach pad 0's copper from
pad 1 -- so the failure is not in the first hop and re-implementing the loop
would just reproduce my own misunderstanding of it.  This wraps rt.astar and
rt.emit and records every call the real route_net() makes: which pad each A*
started from, how big the goal mask was, how many start nodes A* dropped, and
what came back.  The failing call's exact (starts, goals) are then replayed
against a flood to say whether the pad was walled in by our own new copper or
was never reachable to begin with.

  python _tp_loop.py ROW0
"""
import collections
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

NET = sys.argv[1] if len(sys.argv) > 1 else "ROW0"

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

pads = rt.pads[NET]
centres = [(round(x, 2), round(y, 2)) for (x, y, _, _) in pads]


def which_pad(starts):
    """Which entry of `pads` these A* start nodes belong to."""
    sl = set((i, j) for (i, j, _) in starts)
    for k, (x, y, nodes, _) in enumerate(pads):
        if sl & set(nodes):
            return k
    return -1


calls = []


orig_astar = rt.astar


def spy_astar(blocked, via_blocked, starts, goals, **kw):
    rec = collections.OrderedDict(
        pad=which_pad(starts),
        nstarts=len(starts),
        dropped=sum(1 for (i, j, l) in starts if blocked[l, i, j]),
        goals=int(goals.sum()),
    )
    goals_dropped = int((goals & blocked).sum())
    p = orig_astar(blocked, via_blocked, starts, goals, **kw)
    rec["goal_blocked"] = goals_dropped
    rec["got"] = None if p is None else len(p)
    rec["blocked_sum"] = int(blocked.sum())
    calls.append(rec)
    if p is None:
        # keep the exact inputs of the failure for replay below
        rec["_starts"] = list(starts)
        rec["_goals"] = goals.copy()
        rec["_blocked"] = blocked.copy()
    return p


emits = []
orig_emit = rt.emit


def spy_emit(net, path, w, blocked, via_blocked, hw):
    n0 = len(rt.new_tracks) if hasattr(rt, "new_tracks") else 0
    orig_emit(net, path, w, blocked, via_blocked, hw)
    emits.append(len(path))


rlog = []
orig_reachable = R.reachable


def spy_reachable(mask, starts, via=None):
    out = orig_reachable(mask, starts, via)
    rlog.append((len(starts), int(mask.sum()), int(out.sum())))
    return out


R.reachable = spy_reachable
rt.astar = spy_astar
rt.emit = spy_emit

ok = rt.route_net(NET)

print("%s -> route_net returned %s    fail_at=%s" % (NET, ok, rt.fail_at))
print("\n%-4s %-18s %-8s %-7s %-9s %-6s %s"
      % ("#", "pad", "starts", "dropped", "goal", "goal_blk", "result"))
for k, r in enumerate(calls):
    print("%-4d %-18s %-8d %-7d %-9d %-6d %s"
          % (k, str(centres[r["pad"]]) if r["pad"] >= 0 else "?", r["nstarts"],
             r["dropped"], r["goals"], r["goal_blocked"],
             "None" if r["got"] is None else "%d cells" % r["got"]))
print("\nemit path lengths: %s" % (emits or "none"))
print("\nreachable() calls: (seeds, |mask|, |result|)")
for k, (ns, nm, nr) in enumerate(rlog):
    print("   %-4d %-6d %-8d %-8d" % (k, ns, nm, nr))

bad = [r for r in calls if r["got"] is None]
if not bad:
    print("\nno A* failure recorded")
    sys.exit(0)

r = bad[0]
blk, st = r["_blocked"], r["_starts"]
print("\n=== replaying the failing call (pad %s)" % (centres[r["pad"]],))
print("goal mask %d cell(s), %d of them blocked" % (r["goals"], r["goal_blocked"]))
print("start nodes %d, %d blocked" % (len(st), r["dropped"]))

# Was the pad ever reachable, or did our own new copper close it off?  Flood
# the free space of *this* blocked mask, allowing vias, from the pad outwards.
free = ~blk & ~rt.edge
seen = np.zeros_like(free)
stack = [(l, i, j) for (i, j, l) in st if free[l, i, j]]
for s in stack:
    seen[s] = True
while stack:
    l, i, j = stack.pop()
    nbrs = [(l, i + di, j + dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    if rt.via_ok(R.mx(i), R.my(j)):
        nbrs.append((1 - l, i, j))
    for (l2, i2, j2) in nbrs:
        if 0 <= i2 < R.NX and 0 <= j2 < R.NY and free[l2, i2, j2] and not seen[l2, i2, j2]:
            seen[l2, i2, j2] = True
            stack.append((l2, i2, j2))
print("free space reachable from that pad now: %d cell(s)" % int(seen.sum()))
print("   free space on the whole board now:   %d cell(s)" % int(free.sum()))
print("   goal cells that flood actually reaches: %d of %d"
      % (int((seen & r["_goals"]).sum()), r["goals"]))
