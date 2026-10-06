"""Pre-flight: how much work is the incremental panel route, and where?

Replicates route_net()'s "is this pad already joined to pad 0?" test exactly --
same `conn`, same `near`, same reachable() -- without routing anything and
without writing.  A net whose pads are all taken needs no copper at all; a net
with stranded pads is real work, and the coordinates say whether the stranded
pads are where the corridor plan assumed they would be.

Run this before _tp_route.py: it is seconds, and it catches a mis-set origin or
a net name that never got its pads.
"""
import sys
import time

import numpy as np
import pcbnew

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel")
import _tp_route as R

t0 = time.time()
board = pcbnew.LoadBoard(R.BOARD)
bb = board.GetBoardEdgesBoundingBox()
print("edges  x %.2f..%.2f  y %.2f..%.2f"
      % (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetRight()),
         pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetBottom())))
print("grid   NX=%d NY=%d NL=%d  = %.0fk cells   (GRID %.2f mm)"
      % (R.NX, R.NY, R.NL, R.NX * R.NY * R.NL / 1000.0, R.GRID))

rt = R.Router(board)
print("router built in %.1fs; %d nets with pads" % (time.time() - t0, len(rt.pads)))
R.absorb(board, rt)
print("absorbed %d track(s) / %d via(s)"
      % (len(rt.frozen), len(rt.frozen_vias)))

todo = [n for n in rt.pads if len(rt.pads[n]) > 1]
todo = [n for n in todo if n in R.ONLY]
missing = sorted(set(R.ONLY) - set(todo))
if missing:
    sys.exit("ONLY names net(s) with nothing to route: " + ", ".join(missing))


def stranded(net):
    """route_net()'s taken[] test, verbatim, with no routing."""
    pads = rt.pads[net]
    conn = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
    near = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
    for (onet, layer, x1, y1, x2, y2, w) in rt.frozen:
        if onet == net:
            R.raster_seg(conn, layer, x1, y1, x2, y2, w / 2.0)
            R.raster_seg(near, layer, x1, y1, x2, y2, w / 2.0 + R.GRID / 2.0)
    for (vnet, vx, vy) in rt.frozen_vias:
        if vnet == net:
            for layer in (0, 1):
                R.raster_circle(conn, layer, vx, vy, R.VIA_D / 2.0)
                R.raster_circle(near, layer, vx, vy,
                                R.VIA_D / 2.0 + R.GRID / 2.0)
    # a pad only lands on conn if its own net's copper is there; land pad 0
    _, _, nodes, layers = pads[0]
    for l in (layers or (0, 1)):
        for (i, j) in nodes:
            conn[l, i, j] = True
    reach = R.reachable(conn, [(i, j, l) for l in (pads[0][3] or (0, 1))
                               for (i, j) in pads[0][2]])
    out = []
    for a, (ax, ay, nodes, layers) in enumerate(pads):
        if a == 0:
            continue
        if not any(reach[l, i, j] and near[l, i, j]
                   for l in (layers or (0, 1)) for (i, j) in nodes):
            out.append((ax, ay))
    return out


def key(n):
    if n.startswith("ROW"):
        return (0, int(n[3:]))
    if n.startswith("CSEL"):
        return (1, int(n[4:]))
    if n.startswith("DRV"):
        return (2, n)
    if n.startswith("IO"):
        return (3, int(n[2:]))
    return (4, n)


print("\n%-10s %5s %5s  %s" % ("net", "pads", "lost", "stranded pad centres"))
tot = 0
clean = 0
for n in sorted(todo, key=key):
    lost = stranded(n)
    tot += len(lost)
    clean += (not lost)
    coords = "  ".join("(%.2f,%.2f)" % p for p in lost[:7])
    if len(lost) > 7:
        coords += "  +%d" % (len(lost) - 7)
    print("%-10s %5d %5d  %s" % (n, len(rt.pads[n]), len(lost), coords))
print("\n%d net(s) already complete, %d pad(s) stranded across %d net(s)"
      % (clean, tot, len(todo) - clean))
print("elapsed %.1fs" % (time.time() - t0))
