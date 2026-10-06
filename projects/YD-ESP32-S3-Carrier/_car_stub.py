"""Strip dead-end copper, using real geometry rather than point equality.

KiCad flagged one track_dangling on IO9 and, once that segment was cut, the
next link of the same chain.  The chain runs (58.000, 63.800) -> (57.400,
64.400) -> (56.200, 64.400) and terminates in empty board: no pad, no via, no
other run of IO9 copper.  IO9 itself is connected by other means, so the chain
is surplus and safe to delete, one link at a time.

The first attempt at this compared endpoints for exact equality and so reported
four +3V3 segments as dangling: their ends land at (62.800, 32.400), which is
0.2 mm from the via at (62.600, 32.400) -- well inside that via's 0.30 mm pad.
Cutting them orphaned the via.  Hence the geometry below: an endpoint is joined
when it falls within viaRadius + hw of a via centre, within the two half-widths
of another segment of the same net and layer, or inside a pad's bounding box.

Removal is not monotone -- cutting one link can orphan its neighbour -- so the
pass repeats until nothing changes.

  python _car_stub.py --dry
  python _car_stub.py
"""
import math
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = BOARD + ".pre-stub.bak"
DRY = "--dry" in sys.argv
EPS = 0.001

board = pcbnew.LoadBoard(BOARD)
TO = pcbnew.ToMM

tracks = [t for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA)]
vias = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]


def ends(t):
    a, c = t.GetStart(), t.GetEnd()
    return (TO(a.x), TO(a.y)), (TO(c.x), TO(c.y))


def seg_dist(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


VINFO = []
for v in vias:
    s = v.GetStart()
    try:
        r = TO(v.GetWidth(pcbnew.F_Cu)) / 2.0
    except Exception:
        r = 0.30
    VINFO.append((v.GetNetname(), (TO(s.x), TO(s.y)), r))

PADS = {}
for f in board.GetFootprints():
    for p in f.Pads():
        bb = p.GetBoundingBox()
        PADS.setdefault(p.GetNetname(), []).append(
            (TO(bb.GetLeft()), TO(bb.GetTop()), TO(bb.GetRight()), TO(bb.GetBottom())))


def joined(pt, net, layer, hw, self_i, alive):
    for k, o in enumerate(tracks):
        if k == self_i or not alive[k] or o.GetNetname() != net or o.GetLayer() != layer:
            continue
        a, c = ends(o)
        # only the *other* track's half-width: the endpoint must sit on that
        # track's copper.  Summing both half-widths let a 0.283 mm gap between
        # two ends read as joined when KiCad still calls the end dangling.
        if seg_dist(pt, a, c) <= TO(o.GetWidth()) / 2.0 + EPS:
            return True
    for vnet, vp, vr in VINFO:
        if vnet == net and math.hypot(pt[0] - vp[0], pt[1] - vp[1]) <= vr + EPS:
            return True
    x, y = pt
    for l, t, r, b in PADS.get(net, []):
        if l - EPS <= x <= r + EPS and t - EPS <= y <= b + EPS:
            return True
    return False


alive = [True] * len(tracks)
removed = []
for _ in range(20):
    cut = False
    for i, t in enumerate(tracks):
        if not alive[i]:
            continue
        net, layer, hw = t.GetNetname(), t.GetLayer(), TO(t.GetWidth()) / 2.0
        if not net:
            continue
        for e, tag in zip(ends(t), ("start", "end")):
            if not joined(e, net, layer, hw, i, alive):
                a, c = ends(t)
                removed.append((net, pcbnew.LayerName(layer), a, c, tag, e))
                alive[i] = False
                cut = True
                break
    if not cut:
        break

print("dead-end track(s) to remove: %d" % len(removed))
for net, lay, (ax, ay), (cx, cy), tag, pt in removed:
    print("   %-6s %-5s (%7.3f,%7.3f)->(%7.3f,%7.3f)  %s (%7.3f,%7.3f) joins nothing"
          % (net, lay, ax, ay, cx, cy, tag, pt[0], pt[1]))

if not removed:
    sys.exit(0)
if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

_keep_alive = []
for i, t in enumerate(tracks):
    if not alive[i]:
        board.Remove(t)
        _keep_alive.append(t)
board.Save(BOARD)
print("saved: removed %d track(s)" % sum(1 for a in alive if not a))
