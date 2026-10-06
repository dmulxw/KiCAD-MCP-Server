"""Is R7.1 (IO10) / R8.1 (IO11) sealed inside a pocket of free space?

route.py says "cannot reach pad" seven times for each, on a pass where those
two nets are the only things to route -- so it is not congestion.  VIA_BAN
covers (43,11)-(74,32), which contains R6..R9 entirely, so both nets must
finish on F.Cu with no via.  This floods the router's own free mask from the
pad's nodes and names the net whose clearance forms the wall.

  python _probe_pocket.py
"""
import collections
import sys
from collections import deque

import numpy as np
import pcbnew

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts")
import route


def flood(free, seeds, cap=400000):
    seen = set(seeds)
    q = deque(seeds)
    while q and len(seen) < cap:
        i, j = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            i2, j2 = i + di, j + dj
            if (i2, j2) in seen:
                continue
            if not (0 <= i2 < route.NX and 0 <= j2 < route.NY):
                continue
            if not free[i2, j2]:
                continue
            seen.add((i2, j2))
            q.append((i2, j2))
    return seen


board = pcbnew.LoadBoard(route.BOARD)
router = route.Router(board)
route.absorb(board, router)

for net, px, py in (("IO10", 54.750, 20.075), ("IO11", 60.000, 20.825),
                    ("IO9", 48.000, 20.825), ("IO12", 65.600, 20.825)):
    w = route.WIDTHS.get(net, route.DEFAULT_W)
    hw = w / 2.0
    m, v = router.blocked_for(net, hw)
    pad = min(router.pads[net], key=lambda p: (p[0] - px) ** 2 + (p[1] - py) ** 2)
    cx, cy, nodes, layers = pad
    print("\n=== %-5s pad (%.3f, %.3f)  nodes=%d  layers=%r  w=%.2f ==="
          % (net, cx, cy, len(nodes), layers, w))
    for l in (layers or (0, 1)):
        free = ~m[l]
        seeds = [(i, j) for (i, j) in nodes if free[i, j]]
        blocked = [(i, j) for (i, j) in nodes if not free[i, j]]
        if not seeds:
            print("   L%d: all %d node(s) blocked -- A* can never land here"
                  % (l, len(nodes)))
            continue
        seen = flood(free, seeds)
        xs = [i for i, _ in seen]
        ys = [j for _, j in seen]
        print("   L%d: %d free node(s), %d blocked; pocket=%d cell(s)  "
              "x[%.2f..%.2f] y[%.2f..%.2f]"
              % (l, len(seeds), len(blocked), len(seen),
                 route.mx(min(xs)), route.mx(max(xs)),
                 route.my(min(ys)), route.my(max(ys))))

        # attribute the wall: which net's clearance cells bound this pocket?
        seen_s = seen
        bnd = set()
        for (i, j) in seen_s:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (i + di, j + dj)
                if n not in seen_s:
                    bnd.add(n)
        tr = route.CLEAR + hw
        hits = collections.Counter()
        detail = {}
        for other, kind, a, lays in router.shapes:
            if other == net or l not in lays:
                continue
            t = np.zeros((route.NL, route.NX, route.NY), dtype=bool)
            if kind == "circle":
                route.raster_circle(t, l, a[0], a[1], a[2] + tr)
            else:
                x0, y0, x1, y1 = a
                route.raster_rect(t, l, x0, y0, x1, y1, tr)
            c = sum(1 for (i, j) in bnd if t[l, i, j])
            if c:
                hits[other] += c
                detail.setdefault(other, []).append(
                    "pad/rect %s at (%.2f,%.2f)"
                    % (kind, a[0] if kind == "circle" else a[0],
                       a[1] if kind == "circle" else a[1]))
        for onet, layer, x1, y1, x2, y2, tw in list(router.tracks) + list(router.frozen):
            if onet == net or layer != l:
                continue
            t = np.zeros((route.NL, route.NX, route.NY), dtype=bool)
            route.raster_seg(t, l, x1, y1, x2, y2, tw / 2.0 + tr)
            c = sum(1 for (i, j) in bnd if t[l, i, j])
            if c:
                hits[onet] += c
                detail.setdefault(onet, []).append(
                    "seg (%.2f,%.2f)-(%.2f,%.2f) w=%.2f" % (x1, y1, x2, y2, tw))
        print("   wall by net: %s" % dict(hits))
        for n, rows in sorted(detail.items(), key=lambda kv: -hits[kv[0]]):
            print("      %-8s %s" % (n, "; ".join(rows[:6])))
