"""Why can a single net not be routed?  Reproduces the router's own masks."""
import importlib.util, sys, numpy as np, pcbnew
spec = importlib.util.spec_from_file_location("R", "_tp_route.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

NET = sys.argv[1]
board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

print("frozen: %d tracks, %d vias" % (len(rt.frozen), len(rt.frozen_vias)))
pads = rt.pads.get(NET, [])
print("%s: %d pads" % (NET, len(pads)))
for b, (x, y, nodes, layers) in enumerate(pads):
    print("  [%d] (%8.3f,%8.3f) nodes=%d layers=%s" % (b, x, y, len(nodes), layers))

w = R.WIDTHS.get(NET, R.DEFAULT_W); hw = w / 2.0
blocked, via_blocked = rt.blocked_for(NET, hw)

print("\npad-node blocking (blocked mask, i.e. trace cannot sit here):")
for b, (x, y, nodes, layers) in enumerate(pads):
    free, tot = 0, 0
    for l in (layers or (0, 1)):
        for (i, j) in nodes:
            tot += 1
            if not blocked[l, i, j]:
                free += 1
    print("  [%d] (%8.3f,%8.3f)  %d/%d free" % (b, x, y, free, tot))

# reproduce route_net's tree
conn = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
def land(entry, mask):
    _, _, nodes, layers = entry
    for l in (layers or (0, 1)):
        for (i, j) in nodes:
            mask[l, i, j] = True
land(pads[0], conn)
near = np.zeros_like(conn)
for (onet, layer, x1, y1, x2, y2, ww) in rt.frozen:
    if onet == NET:
        R.raster_seg(conn, layer, x1, y1, x2, y2, ww / 2.0)
        R.raster_seg(near, layer, x1, y1, x2, y2, ww / 2.0 + R.GRID / 2.0)
for (vnet, vx, vy) in rt.frozen_vias:
    if vnet == NET:
        for layer in (0, 1):
            R.raster_circle(conn, layer, vx, vy, R.VIA_D / 2.0)
            R.raster_circle(near, layer, vx, vy, R.VIA_D / 2.0 + R.GRID / 2.0)

def seed():
    return [(i, j, l) for l in (pads[0][3] or (0, 1)) for (i, j) in pads[0][2]]
reach = R.reachable(conn, seed(), rt.via_ok)
print("\nconn cells: %d   reach cells (from pads[0]): %d"
      % (conn.sum(), reach.sum()))
idx = np.argwhere(reach)
if len(idx):
    ls, iis, jjs = idx[:, 0], idx[:, 1], idx[:, 2]
    print("  reach bbox: x %.2f..%.2f  y %.2f..%.2f  layers %s"
          % (R.mx(iis.min()), R.mx(iis.max()), R.my(jjs.min()), R.my(jjs.max()),
             sorted(set(ls))))

taken = [b == 0 or any(reach[l, i, j] and near[l, i, j]
                       for l in (pads[b][3] or (0, 1))
                       for (i, j) in pads[b][2])
         for b in range(len(pads))]
print("\ntaken[] =", taken)

best, bestd = None, 1e18
for a, (ax, ay, _, _) in enumerate(pads):
    if taken[a]: continue
    for b, (bx, by, _, _) in enumerate(pads):
        if not taken[b]: continue
        d = (ax - bx) ** 2 + (ay - by) ** 2
        if d < bestd: bestd, best = d, a
print("next pad to hook up: [%d] %s (d=%.2f mm)" % (best, pads[best][:2], bestd ** 0.5))

_, _, nodes, layers = pads[best]
starts = [(i, j, l) for l in (layers or (0, 1)) for (i, j) in nodes]
before = blocked.copy()
ok_starts = [s for s in starts if not blocked[s[2], s[0], s[1]]]
print("  starts: %d total, %d unblocked" % (len(starts), len(ok_starts)))
path = rt.astar(blocked, via_blocked, starts, reach)
print("  astar -> %s" % ("None" if path is None else "%d nodes" % len(path)))
if path is not None:
    print("    from (%s) to (%s)"
          % (R.mx(path[0][0]), R.my(path[0][1])), end="")
    print(" (%s,%s) layer %s -> %s" % (R.mx(path[-1][0]), R.my(path[-1][1]),
                                       path[-1][2], path[0][2]))

# how big is the free region around the failing pad?
from collections import deque
if path is None:
    i0, j0, l0 = starts[0]
    seen = np.zeros_like(blocked)
    q = deque()
    if not blocked[l0, i0, j0]:
        seen[l0, i0, j0] = True; q.append((l0, i0, j0))
    else:
        for (l, i, j) in starts:
            if not blocked[l, i, j] and not seen[l, i, j]:
                seen[l, i, j] = True; q.append((l, i, j))
    while q:
        l, i, j = q.popleft()
        for di, dj in R.NB if hasattr(R, "NB") else ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            i2, j2 = i + di, j + dj
            if 0 <= i2 < R.NX and 0 <= j2 < R.NY and not blocked[l, i2, j2] and not seen[l, i2, j2]:
                seen[l, i2, j2] = True; q.append((l, i2, j2))
        if not via_blocked[l, i, j]:
            l2 = 1 - l
            if not blocked[l2, i, j] and not seen[l2, i, j]:
                seen[l2, i, j] = True; q.append((l2, i, j))
    c = np.argwhere(seen)
    print("  free region reachable from start (no layer-change cost): %d cells" % len(c))
    if len(c):
        print("    bbox x %.2f..%.2f  y %.2f..%.2f  layers %s"
              % (R.mx(c[:,1].min()), R.mx(c[:,1].max()),
                 R.my(c[:,2].min()), R.my(c[:,2].max()), sorted(set(c[:,0]))))
        print("    touches reach? %s" % bool((seen & reach).any()))
