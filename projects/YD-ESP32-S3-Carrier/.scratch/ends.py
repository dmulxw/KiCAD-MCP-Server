"""Which end of the failing connection is actually sealed?

route_net() searches from the pad it is hooking up *towards* the tree it already
has, so when A* fails it is the tree that is unreachable -- but fail_at names the
pad it started from, which is usually wide open.  Run the search both ways and see
which direction is the one that has no path.
"""
import importlib.util
import sys

import numpy as np
import pcbnew

spec = importlib.util.spec_from_file_location(
    "route", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts\route.py")
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)

board = pcbnew.LoadBoard(route.BOARD)
_keep = route.clear_routing(board)
router = route.Router(board)

todo = [n for n in router.pads if n != "GND" and len(router.pads[n]) > 1]


def span(net):
    pts = router.pads[net]
    return ((max(p[0] for p in pts) - min(p[0] for p in pts)) ** 2
            + (max(p[1] for p in pts) - min(p[1] for p in pts)) ** 2) ** 0.5


todo.sort(key=span)
failed = route.route_all(router, todo)
print(f"\nspan asc -> failed: {failed}\n")


def box(nodes, layers, l, i0, i1, j0, j1):
    m = np.zeros((route.NL, route.NX, route.NY), dtype=bool)
    for lay in (layers or (0, 1)):
        for (i, j) in nodes:
            m[lay, i, j] = True
    return m


for net in (sys.argv[1:] or failed):
    if net not in router.pads:
        continue
    w = route.WIDTHS.get(net, route.DEFAULT_W)
    hw = w / 2.0

    r2 = route.Router(board)
    r2.tracks, r2.vias = list(router.tracks), list(router.vias)
    route.rip(r2, {net})
    blocked, vblk = r2.blocked_for(net, hw)
    pads = r2.pads[net]
    print(f"=== {net}  w={w}  {len(pads)} pad(s)")

    for k, (cx, cy, nodes, layers) in enumerate(pads):
        ls = layers or (0, 1)
        free = sum(1 for l in ls for (i, j) in nodes if not blocked[l, i, j])
        print(f"    pad{k} ({cx:7.3f},{cy:7.3f}) layers={ls}  "
              f"{free}/{len(nodes) * len(ls)} landing node(s) free")

    # search from pad0 to pad1 and back again
    for a, b in ((0, 1), (1, 0)):
        _, _, na, la = pads[a]
        _, _, nb, lb = pads[b]
        starts = [(i, j, l) for l in (la or (0, 1)) for (i, j) in na]
        goals = np.zeros((route.NL, route.NX, route.NY), dtype=bool)
        for l in (lb or (0, 1)):
            for (i, j) in nb:
                goals[l, i, j] = True
        path = r2.astar(blocked, vblk, starts, goals)
        print(f"    pad{a} -> pad{b}: {'OK, %d nodes' % len(path) if path else 'NO PATH'}")
    print()
