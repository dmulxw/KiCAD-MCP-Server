"""Where along the corridor does A* actually get stopped?

The stall point is the pad it could not reach, and that pad is usually wide open --
so the wall is somewhere between the two.  Draw the whole region the net spans, with
its own pads marked, and the blockage becomes visible.
"""
import importlib.util
import sys

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

for net in (sys.argv[1:] or failed):
    if net not in router.pads:
        continue
    w = route.WIDTHS.get(net, route.DEFAULT_W)
    hw = w / 2.0

    r2 = route.Router(board)
    r2.tracks, r2.vias = list(router.tracks), list(router.vias)
    route.rip(r2, {net})
    ok = r2.route_net(net)
    if ok:
        print(f"=== {net}: routes fine against the finished board")
        continue

    at = r2.fail_at
    b, _ = r2.blocked_for(net, hw)
    pads = r2.pads[net]
    print(f"=== {net}  w={w}  halo={route.CLEAR + hw:.2f}  stalls at {at}")
    print(f"    pads: {[(round(p[0], 2), round(p[1], 2)) for p in pads]}")

    # Window: the failing pad, widened to take in the nearest pad on the side the
    # signal comes from.  `WX` (mm) is how far to look along x either way.
    WX = float(sys.argv[2]) if len(sys.argv) > 2 else 13.0
    near = sorted(pads, key=lambda p: abs(p[1] - at[1]))[:2]
    ys = [p[1] for p in near]
    i0, i1 = route.gi(at[0] - WX), route.gi(at[0] + WX)
    j0, j1 = route.gj(min(ys) - 2.0), route.gj(max(ys) + 2.0)
    print(f"    x {route.mx(i0):.2f}..{route.mx(i1):.2f}   y {route.my(j0):.2f}..{route.my(j1):.2f}")

    # where the net's own pads are, so the picture can be read
    cell = {}
    for (cx, cy, nodes, layers) in pads:
        for l in (layers or (0, 1)):
            for (i, j) in nodes:
                cell[(l, i, j)] = "o"

    for l in (0, 1):
        print(f"    -- layer {l} --   ('o' = this net's own pad, '#' = blocked)")
        for j in range(j0, j1 + 1):
            row = []
            for i in range(i0, i1 + 1):
                if (l, i, j) in cell:
                    row.append("o")
                elif b[l, i, j]:
                    row.append("#")
                else:
                    row.append(".")
            print(f"      y={route.my(j):6.2f} {''.join(row)}")
    print()
