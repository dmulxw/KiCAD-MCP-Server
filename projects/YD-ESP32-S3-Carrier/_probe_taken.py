"""Why did route_net() call IO9 done with zero segments?

route.py reported [OK] IO9 and [OK] IO12 with 0 segs while DRC still lists both
as unconnected, and IO10/IO11 as unreachable.  Both symptoms point at the
`taken[]` predicate -- the one that decides a pad is already on the net's copper
-- so this reproduces it in isolation and prints the decision per pad.

route.py only runs main() under __main__, so it imports cleanly.

  python _probe_taken.py
"""
import numpy as np
import pcbnew
import sys

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts")
import route

board = pcbnew.LoadBoard(route.BOARD)
router = route.Router(board)
route.absorb(board, router)

print("frozen: %d track(s), %d via(s)"
      % (len(router.frozen), len(router.frozen_vias)))

for net in ("IO9", "IO10", "IO11", "IO12", "+3V3"):
    pads = router.pads.get(net, [])
    print("\n%s: %d pad(s)" % (net, len(pads)))
    for k, (cx, cy, nodes, layers) in enumerate(pads):
        print("   [%d] (%7.2f, %7.2f)  %2d node(s)  layers=%s"
              % (k, cx, cy, len(nodes), layers))

    if len(pads) < 2:
        print("   -> route_net returns True immediately (len < 2)")
        continue

    w = route.WIDTHS.get(net, route.DEFAULT_W)
    hw = w / 2.0
    blocked, via_blocked = router.blocked_for(net, hw)
    conn = np.zeros((route.NL, route.NX, route.NY), dtype=bool)

    # replicate route_net exactly
    p0 = pads[0]
    for l in (p0[3] or (0, 1)):
        for (i, j) in p0[2]:
            conn[l, i, j] = True
    near = np.zeros((route.NL, route.NX, route.NY), dtype=bool)
    n_frozen = 0
    for (onet, layer, x1, y1, x2, y2, fw) in router.frozen:
        if onet == net:
            n_frozen += 1
            route.raster_seg(conn, layer, x1, y1, x2, y2, fw / 2.0)
            route.raster_seg(near, layer, x1, y1, x2, y2,
                             fw / 2.0 + route.GRID / 2.0)
    for (vnet, vx, vy) in router.frozen_vias:
        if vnet == net:
            n_frozen += 1
            for layer in (0, 1):
                route.raster_circle(conn, layer, vx, vy, route.VIA_D / 2.0)
                route.raster_circle(near, layer, vx, vy,
                                    route.VIA_D / 2.0 + route.GRID / 2.0)
    print("   frozen pieces of this net: %d   conn cells: %d"
          % (n_frozen, int(conn.sum())))

    reach = route.reachable(conn, [(i, j, l) for l in (p0[3] or (0, 1))
                                   for (i, j) in p0[2]])
    print("   reach cells: %d" % int(reach.sum()))
    for a, (cx, cy, nodes, layers) in enumerate(pads):
        hit = any(reach[l, i, j] and near[l, i, j]
                  for l in (layers or (0, 1)) for (i, j) in nodes)
        on_reach = any(reach[l, i, j]
                       for l in (layers or (0, 1)) for (i, j) in nodes)
        on_near = any(near[l, i, j]
                      for l in (layers or (0, 1)) for (i, j) in nodes)
        print("   [%d] (%7.2f,%7.2f) taken=%-5s  on_reach=%-5s on_near=%-5s"
              % (a, cx, cy, a == 0 or hit, on_reach, on_near))
