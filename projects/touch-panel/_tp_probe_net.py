"""Instrument route_net()'s own variables for one net.

_tp_gap.py floods the *free* space, which answers "is there a way through" but
not "can A* get there": A* only enters a cell whose `blocked` bit is clear, and
only accepts a goal cell it was able to push, so a goal sitting under `blocked`
is unreachable no matter how open the board around it looks.  This reproduces
route_net()'s setup exactly and prints the pieces it actually uses -- `conn`
after landing pad 0, the pad-0-reachable subset `reach` that A* is now given as
its goal, which pads on_tree() calls taken, and the straight rt.astar() calls
for both goal masks, so the difference between them is visible.

  python _tp_probe_net.py ROW0
"""
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

w = R.WIDTHS.get(NET, R.DEFAULT_W)
blocked, via_blocked = rt.blocked_for(NET, w / 2.0)
pads = rt.pads[NET]

# --- route_net()'s setup, verbatim -----------------------------------------
conn = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
near = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
nfr = 0
for (onet, layer, x1, y1, x2, y2, ww) in rt.frozen:
    if onet == NET:
        nfr += 1
        R.raster_seg(conn, layer, x1, y1, x2, y2, ww / 2.0)
        R.raster_seg(near, layer, x1, y1, x2, y2, ww / 2.0 + R.GRID / 2.0)
for (vnet, vx, vy) in rt.frozen_vias:
    if vnet == NET:
        for layer in (0, 1):
            R.raster_circle(conn, layer, vx, vy, R.VIA_D / 2.0)
            R.raster_circle(near, layer, vx, vy, R.VIA_D / 2.0 + R.GRID / 2.0)
n_conn = int(conn.sum())


def land(entry, mask):
    _, _, nodes, layers = entry
    for l in (layers or (0, 1)):
        for (i, j) in nodes:
            mask[l, i, j] = True


land(pads[0], conn)
print("%s  w=%.2f   %d pad(s), %d frozen segment(s)"
      % (NET, w, len(pads), nfr))
print("conn: %d cell(s) of frozen copper, %d after landing pad 0 (+%d)"
      % (n_conn, int(conn.sum()), int(conn.sum()) - n_conn))

seed = [(i, j, l) for l in (pads[0][3] or (0, 1)) for (i, j) in pads[0][2]]
reach = R.reachable(conn, seed)
nreach = int(reach.sum())
print("\npad 0 = (%7.2f,%7.2f) layers=%s  %d node(s)"
      % (pads[0][0], pads[0][1], pads[0][3], len(pads[0][2])))
print("reach = %d cell(s) -- %.1f%% of conn is joined to pad 0"
      % (nreach, 100.0 * nreach / max(1, int(conn.sum()))))
nb = int((reach & blocked).sum())
print("   %d of them sit under `blocked`, where A* may never stand%s"
      % (nb, "   <-- GOAL UNREACHABLE" if nb == nreach else ""))
ri, rj, rl = np.where(reach)
if len(ri):
    print("   reach spans x %.2f..%.2f  y %.2f..%.2f  layer(s) %s"
          % (R.mx(ri.min()), R.mx(ri.max()), R.my(rj.min()), R.my(rj.max()),
             sorted(set(rl.tolist()))))

# --- which pads does taken[] call done? ------------------------------------
print("\n%-4s %-18s %-9s %-8s %-9s %s"
      % ("pad", "at", "on_reach", "on_near", "taken", "start nodes blocked"))
taken = []
for b, (x, y, nodes, layers) in enumerate(pads):
    ls = layers or (0, 1)
    onr = any(reach[l, i, j] for l in ls for (i, j) in nodes)
    onn = any(near[l, i, j] for l in ls for (i, j) in nodes)
    tak = b == 0 or (onr and onn)
    taken.append(tak)
    nbad = sum(blocked[l, i, j] for l in ls for (i, j) in nodes)
    print("%-4d (%7.2f,%7.2f) %-9s %-8s %-9s %d/%d"
          % (b, x, y, onr, onn, tak, nbad, len(nodes) * len(ls)))

print("\ntaken = %s   done = %d of %d"
      % ("".join("1" if t else "0" for t in taken), sum(taken), len(pads)))

# --- the pad the Prim step picks, and the A* call itself --------------------
best, bestd = None, 1e18
for a, (ax, ay, _, _) in enumerate(pads):
    if taken[a]:
        continue
    for b, (bx, by, _, _) in enumerate(pads):
        if not taken[b]:
            continue
        d = (ax - bx) ** 2 + (ay - by) ** 2
        if d < bestd:
            bestd, best = d, a
if best is None:
    print("\nno Prim step needed")
    sys.exit(0)
print("\nPrim would pick pad %d (%7.2f,%7.2f)"
      % (best, pads[best][0], pads[best][1]))

_, _, nodes, layers = pads[best]
starts = [(i, j, l) for l in (layers or (0, 1)) for (i, j) in nodes]
nbad = sum(1 for (i, j, l) in starts if blocked[l, i, j])
print("   %d start node(s), %d blocked (A* silently drops those)"
      % (len(starts), nbad))

for label, goal in (("reach", reach), ("conn", conn)):
    p = rt.astar(blocked, via_blocked, starts, goal)
    print("   astar(goal=%-6s) -> %s"
          % (label, "None" if p is None else "%d cell(s)" % len(p)))
