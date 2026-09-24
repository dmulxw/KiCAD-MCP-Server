"""Is the last failure congestion or geometry?

Rip up every other net and try the straggler on a bare board.  If it still fails,
no amount of ordering or rip-up will help and the mask itself is wrong.
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

for net in ("IO13", "IO14", "+5V"):
    r = route.Router(board)
    ok = r.route_net(net)
    print(f"{net:<6} alone on an empty board -> {ok}  "
          f"({sum(1 for t in r.tracks if t[0] == net)} segs)")

# If a net fails alone, show the mask around the pad it could not reach.
r = route.Router(board)
for net in ("IO13", "IO14", "+5V"):
    r.route_net(net)
    if r.fail_at is None:
        continue
    cx, cy = r.fail_at
    w = route.WIDTHS.get(net, route.DEFAULT_W)
    blocked, _ = r.blocked_for(net, w / 2.0)
    print(f"\n=== {net} stalled at ({cx}, {cy}), w={w}, hw={w/2.0}")
    for l in (0, 1):
        i, j = route.gi(cx), route.gj(cy)
        row = "".join("#" if blocked[l, i + d, j] else "." for d in range(-6, 7))
        col = "".join("#" if blocked[l, i, j + d] else "." for d in range(-6, 7))
        print(f"    layer {l}  row(i-6..i+6) {row}   col(j-6..j+6) {col}")
    # which static shapes own those cells?
    owners = []
    for (onet, kind, a, layers) in r.shapes:
        if kind == "circle":
            if abs(a[0] - cx) < 4 and abs(a[1] - cy) < 4:
                owners.append((onet, "circle", a, layers))
        else:
            if a[0] - 4 < cx < a[2] + 4 and a[1] - 4 < cy < a[3] + 4:
                owners.append((onet, "rect", a, layers))
    for o in owners:
        print(f"    static: net={o[0] or '-'} {o[1]} {tuple(round(v, 3) for v in o[2])} layers={o[3]}")
