"""Why did rip-up not repair the last few nets?

Runs the real pipeline, then asks blocking_nets() what it saw for each straggler --
None means the cap was hit (too much in the way to gamble on), a short list means the
rip-and-retry was attempted and still failed.
"""
import importlib.util

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
print(f"\nfailed: {failed}")

for net in ("IO14", "IO12", "IO13", "+5V"):
    if net not in failed:
        continue
    print(f"\n=== {net}")
    for (cx, cy, nodes, layers) in router.pads[net]:
        blocked, vblk = router.blocked_for(net, route.WIDTHS.get(net, route.DEFAULT_W) / 2.0)
        free = sum(1 for l in (layers or (0, 1)) for (i, j) in nodes if not blocked[l, i, j])
        tot = len(nodes) * len(layers or (0, 1))
        print(f"    pad ({cx:7.3f},{cy:7.3f})  {free}/{tot} node(s) free")
    v = route.blocking_nets(router, net)
    print(f"    blocking_nets -> {'CAP HIT (None)' if v is None else v}")

    # what is *actually* sitting on the failed pad, in the raw mask?
    entry = router.pads[net][-1]
    cx, cy, nodes, layers = entry
    blocked, _ = router.blocked_for(net, route.WIDTHS.get(net, route.DEFAULT_W) / 2.0)
    near = set()
    for (onet, _l, ax, ay, bx, by, w) in router.tracks:
        if onet == net:
            continue
        if min(ax, bx) - 2 <= cx <= max(ax, bx) + 2 and min(ay, by) - 2 <= cy <= max(ay, by) + 2:
            near.add(onet)
    for (vnet, vx, vy) in router.vias:
        if vnet != net and abs(vx - cx) <= 2 and abs(vy - cy) <= 2:
            near.add(vnet)
    print(f"    copper of {sorted(near)} within 2 mm of that pad")
