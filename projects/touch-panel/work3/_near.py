"""What is sealing a pocket?  Print every piece of copper near a point.

    python _near.py <board> <x> <y> [radius]

Item, net, layer, real endpoints (not bbox), and the distance from the query
point, sorted by distance.  This is the honest answer to "A* says no path but
the goal is a millimetre away" -- the obstacle set is the only thing that can
seal a pocket, so print the obstacle set.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402

S = 1e6
board = pcbnew.LoadBoard(sys.argv[1])
qx, qy = float(sys.argv[2]), float(sys.argv[3])
R = float(sys.argv[4]) if len(sys.argv) > 4 else 6.0


def seg_dist(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return ((x - a[0]) ** 2 + (y - a[1]) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
    return ((x - (a[0] + t * dx)) ** 2 + (y - (a[1] + t * dy)) ** 2) ** 0.5


rows = []
for o, ref in ([(t, None) for t in board.GetTracks()]
               + [(p, f.GetReference()) for f in board.GetFootprints()
                  for p in f.Pads()]):
    if isinstance(o, pcbnew.PAD):
        bb = o.GetBoundingBox()
        ax, ay = bb.GetLeft() / S, bb.GetTop() / S
        bx, by = bb.GetRight() / S, bb.GetBottom() / S
        lay = "/".join(l for l, c in (("F.Cu", pcbnew.F_Cu), ("B.Cu", pcbnew.B_Cu))
                       if o.IsOnLayer(c))
        desc = "PAD %s.%s" % (ref, o.GetNumber())
        dx = max(ax - qx, 0.0, qx - bx)
        dy = max(ay - qy, 0.0, qy - by)
        d = (dx * dx + dy * dy) ** 0.5
    elif isinstance(o, pcbnew.PCB_VIA):
        bb = o.GetBoundingBox()
        ax, ay = bb.GetLeft() / S, bb.GetTop() / S
        bx, by = bb.GetRight() / S, bb.GetBottom() / S
        lay, desc = "THRU", "VIA"
        dx = max(ax - qx, 0.0, qx - bx)
        dy = max(ay - qy, 0.0, qy - by)
        d = (dx * dx + dy * dy) ** 0.5
    else:
        s, e = o.GetStart(), o.GetEnd()
        ax, ay, bx, by = s.x / S, s.y / S, e.x / S, e.y / S
        lay = "/".join(l for l, c in (("F.Cu", pcbnew.F_Cu), ("B.Cu", pcbnew.B_Cu))
                       if o.IsOnLayer(c))
        desc = "TRK"
        d = seg_dist(qx, qy, (ax, ay), (bx, by))
    if d - R > 0:
        continue
    rows.append((d, desc, o.GetNetname(), lay, ax, ay, bx, by, o.GetLayer()))

rows.sort(key=lambda r: r[0])
print("copper within %.1fmm of (%.3f, %.3f) on %s" % (R, qx, qy, sys.argv[1]))
for d, desc, net, lay, ax, ay, bx, by, lyr in rows:
    print("  %6.3f  %-12s %-8s %-8s (%8.3f,%8.3f)->(%8.3f,%8.3f) L=%d"
          % (d, desc, net, lay, ax, ay, bx, by, lyr))
print("%d item(s)" % len(rows))
