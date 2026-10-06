"""Full 3-D flood (both copper layers + via transitions) from R7.1 and from J8.2.

_probe_pocket.py flooded F.Cu alone and found a sealed 2665-cell pocket.  That
was misleading: route_net calls astar(blocked, via_blocked, ...) without
vias_banned=True, so VIA_BAN never applies and a via is legal wherever
via_blocked is clear on both layers.  This is the honest test -- if R7.1 and
J8.2 are in different components here, IO10 is unroutable as constrained.

  python _probe_3d.py
"""
import sys
from collections import deque

import numpy as np
import pcbnew

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts")
import route

NET = "IO10"


def flood3(blocked, via_blocked, seeds, cap=1500000):
    """4-connect within a layer; change layer where via_blocked clears both."""
    seen = set(seeds)
    q = deque(seeds)
    while q and len(seen) < cap:
        i, j, l = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            i2, j2 = i + di, j + dj
            if (i2, j2, l) in seen or not (0 <= i2 < route.NX and 0 <= j2 < route.NY):
                continue
            if blocked[l, i2, j2]:
                continue
            seen.add((i2, j2, l))
            q.append((i2, j2, l))
        l2 = 1 - l
        if (i, j, l2) not in seen and not via_blocked[l, i, j] and not via_blocked[l2, i, j]:
            seen.add((i, j, l2))
            q.append((i, j, l2))
    return seen


board = pcbnew.LoadBoard(route.BOARD)
router = route.Router(board)
route.absorb(board, router)

w = route.WIDTHS.get(NET, route.DEFAULT_W)
hw = w / 2.0
blocked, via_blocked = router.blocked_for(NET, hw)
print("%s  w=%.2f  grid %dx%dx%d" % (NET, w, route.NL, route.NX, route.NY))

pads = router.pads[NET]
print("pads:")
for k, (cx, cy, nodes, layers) in enumerate(pads):
    print("   [%d] (%7.3f, %7.3f)  %2d node(s)  layers=%s" % (k, cx, cy, len(nodes), layers))

comps = []
for k, (cx, cy, nodes, layers) in enumerate(pads):
    seeds = [(i, j, l) for l in (layers or (0, 1)) for (i, j) in nodes
             if not blocked[l, i, j]]
    if not seeds:
        print("   [%d] every node blocked -- unreachable by construction" % k)
        comps.append((k, None, set()))
        continue
    seen = flood3(blocked, via_blocked, seeds)
    xs = [i for i, _, _ in seen]
    ys = [j for _, j, _ in seen]
    n0 = sum(1 for c in seen if c[2] == 0)
    print("   [%d] at (%7.2f,%7.2f): component %7d cell(s)  (F.Cu %d / B.Cu %d)"
          "  x[%5.1f..%5.1f] y[%5.1f..%5.1f]"
          % (k, cx, cy, len(seen), n0, len(seen) - n0,
             route.mx(min(xs)), route.mx(max(xs)),
             route.my(min(ys)), route.my(max(ys))))
    comps.append((k, seen, set()))

print("\npairwise same-component?")
for a in range(len(pads)):
    for b in range(a + 1, len(pads)):
        sa, sb = comps[a][1], comps[b][1]
        if sa is None or sb is None:
            verdict = "n/a (blocked seed)"
        elif next(iter(sb)) in sa:
            verdict = "YES"
        else:
            verdict = "no"
        print("   [%d]-[%d] (%.1f,%.1f)-(%.1f,%.1f): %s"
              % (a, b, pads[a][0], pads[a][1], pads[b][0], pads[b][1], verdict))
