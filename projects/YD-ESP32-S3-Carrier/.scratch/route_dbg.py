"""Why did A* give up?  Re-run the router's own loop and dump the state at the
first failing net: which pads it could not reach, how many start nodes were free,
and whether any goal node was left unblocked.
"""
import importlib.util
import sys

import numpy as np
import pcbnew

spec = importlib.util.spec_from_file_location(
    "route", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts\route.py")
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)          # main() is guarded, so this is inert

WANT = sys.argv[1:] or ["IO9", "BTN_VOL_UP", "I2S_BCK", "+5V"]

board = pcbnew.LoadBoard(route.BOARD)
# Hold the proxies: dropping them frees board-owned objects out from under SWIG and
# the next GetFootprints() hands back raw SwigPyObjects.
_keep = route.clear_routing(board)
router = route.Router(board)

todo = [n for n in router.pads if n != "GND" and len(router.pads[n]) > 1]


def span(net):
    pts = router.pads[net]
    return ((max(p[0] for p in pts) - min(p[0] for p in pts)) ** 2
            + (max(p[1] for p in pts) - min(p[1] for p in pts)) ** 2) ** 0.5


todo.sort(key=lambda n: (-route.WIDTHS.get(n, route.DEFAULT_W), -span(n)))

for net in todo:
    w = route.WIDTHS.get(net, route.DEFAULT_W)
    if net in WANT:
        pads = router.pads[net]
        print(f"\n=== {net}  w={w:.2f}  {len(pads)} pad(s)")
        for (cx, cy, nodes, layers) in pads:
            print(f"    pad ({cx:7.3f},{cy:7.3f})  layers={layers}  "
                  f"{len(nodes)} node(s): {nodes[:4]}")
        # reproduce route_net's first hookup against the *pristine* mask
        hw = w / 2.0
        blocked, vblk = router.blocked_for(net, hw)
        p0 = pads[0]
        print(f"    pad0 nodes blocked? "
              f"{[bool(blocked[l, i, j]) for l in (p0[3] or (0, 1)) for (i, j) in p0[2]]}")
        for a in range(1, len(pads)):
            _, _, nodes, layers = pads[a]
            free = sum(1 for l in (layers or (0, 1)) for (i, j) in nodes
                       if not blocked[l, i, j])
            print(f"    pad{a} ({pads[a][0]:7.3f},{pads[a][1]:7.3f})  "
                  f"{free}/{len(nodes) * len(layers or (0, 1))} start node(s) free")
    if net in WANT:
        break

# how far does the real thing get, and what does it hit?
for net in WANT:
    if net not in router.pads:
        print(f"\n{net}: not a routed net")
        continue
    w = route.WIDTHS.get(net, route.DEFAULT_W)
    ok = router.route_net(net)
    n = sum(1 for t in router.tracks if t[0] == net)
    print(f"{net:<12} route_net -> {ok}   {n} seg(s)")
