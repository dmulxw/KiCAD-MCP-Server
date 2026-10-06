"""Is R7.1 trapped by placement, or just outbid for the one doorway?

The pocket flood (_probe_pocket.py) is taken against the board as it stands, so
it cannot say whether the wall is *permanent* (placement) or *another net's
routing* (a conflict the router could resolve by re-ordering).  This rebuilds
the router's own obstacle mask from scratch, subtracting one net at a time, and
re-floods.  If dropping IO12's copper opens the pocket to the whole board, the
parts are fine and only the routing order is wrong.

  python _probe_open.py
"""
import sys
from collections import deque

import numpy as np
import pcbnew

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts")
import route

import sys
NET = sys.argv[1]
PX, PY = float(sys.argv[2]), float(sys.argv[3])


def flood(free, seeds, cap=2000000):
    seen = set(seeds)
    q = deque(seeds)
    while q and len(seen) < cap:
        i, j = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            i2, j2 = i + di, j + dj
            if (i2, j2) in seen or not (0 <= i2 < route.NX and 0 <= j2 < route.NY):
                continue
            if not free[i2, j2]:
                continue
            seen.add((i2, j2))
            q.append((i2, j2))
    return seen


board = pcbnew.LoadBoard(route.BOARD)
router = route.Router(board)
route.absorb(board, router)

w = route.WIDTHS.get(NET, route.DEFAULT_W)
hw = w / 2.0
tr = route.CLEAR + hw
pad = min(router.pads[NET], key=lambda p: (p[0] - PX) ** 2 + (p[1] - PY) ** 2)
cx, cy, nodes, layers = pad
layer = list(layers)[0]

allnets = sorted({n for n, _k, _a, _l in router.shapes} |
                 {t[0] for t in list(router.tracks) + list(router.frozen)} |
                 {v[0] for v in list(router.vias) + list(router.frozen_vias)})
print("nets present: %d" % len(allnets))


def mask_without(skip):
    m = router.edge.copy()
    for other, kind, a, lays in router.shapes:
        if other == NET or other in skip or layer not in lays:
            continue
        if kind == "circle":
            route.raster_circle(m, layer, a[0], a[1], a[2] + tr)
        else:
            route.raster_rect(m, layer, a[0], a[1], a[2], a[3], tr)
    for onet, l, x1, y1, x2, y2, tw in list(router.tracks) + list(router.frozen):
        if onet == NET or onet in skip or l != layer:
            continue
        route.raster_seg(m, layer, x1, y1, x2, y2, tw / 2.0 + tr)
    for vnet, vx, vy in list(router.vias) + list(router.frozen_vias):
        if vnet == NET or vnet in skip:
            continue
        route.raster_circle(m, layer, vx, vy, route.VIA_D / 2.0 + tr)
    return m


sets = [
    (),
    ("IO12",),
    ("IO9", "IO12"),
    ("+5V",),
    ("+3V3",),
    ("IO12", "+5V"),
    ("IO12", "+3V3"),
    ("IO11", "IO12"),
    ("IO9", "IO11", "IO12"),
    ("IO9", "IO11", "IO12", "+5V"),
    ("IO9", "IO11", "IO12", "+5V", "+3V3"),
]

print("\n%-40s %10s  %s" % ("drop these nets", "pocket", "bbox (mm)"))
for skip in sets:
    m = mask_without(set(skip))
    free = ~m[layer]
    seeds = [(i, j) for (i, j) in nodes if free[i, j]]
    if not seeds:
        print("%-40s %10s" % (", ".join(skip) or "(nothing)", "SEALED PAD"))
        continue
    seen = flood(free, seeds)
    xs = [i for i, _ in seen]
    ys = [j for _, j in seen]
    print("%-40s %10d  x[%.1f..%.1f] y[%.1f..%.1f]"
          % (", ".join(skip) or "(nothing)", len(seen),
             route.mx(min(xs)), route.mx(max(xs)),
             route.my(min(ys)), route.my(max(ys))))
