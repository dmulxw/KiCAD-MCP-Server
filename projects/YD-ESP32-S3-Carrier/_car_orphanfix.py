"""Tie the orphaned F.Cu ground islands back into the main ground body.

The pour left three F.Cu islands that no path reaches.  A "does this island
contain a GND item?" test cannot see them, because the items they contain are
themselves only attached to that island: one island owns a lone pad, another
shares a via with a B.Cu island that is equally stranded.  Each island looks
populated; the group is still an orphan.

So this builds the real graph -- union-find over islands, vias, pads and tracks
-- finds the component carrying the bulk of the ground (220 of the 221 vias),
and then stitches every island outside it back in.  Each repair is a via laid
where the orphan's F.Cu fill overlaps copper belonging to that main component
on B.Cu, so the via's barrel welds the two together.

The landing point is only accepted if a disc of the via's full diameter plus a
margin fits inside *both* pieces of copper.  That is what keeps the new via
from breaking clearance: the ground fill already stands off every other net, so
a via that fits inside it cannot reach anything else.

  python _car_orphanfix.py               # report only
  python _car_orphanfix.py --fix         # place the vias, refill, save
"""
import argparse
import collections
import math
import shutil

import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
BAK = BOARD + ".pre-orphanfix.bak"

TO = pcbnew.ToMM
F_CU, B_CU = pcbnew.F_Cu, pcbnew.B_Cu
LAYERS = (F_CU, B_CU)

VIA_D = 0.60
VIA_DRILL = 0.30
MARGIN = 0.05
R = VIA_D / 2.0 + MARGIN
STEP = 0.20
CROWD = 0.60          # stay this far from an existing GND via
ANGLES = [(math.cos(a * math.pi / 4.0), math.sin(a * math.pi / 4.0)) for a in range(8)]

ap = argparse.ArgumentParser()
ap.add_argument("--fix", action="store_true", help="place the vias and save")
args = ap.parse_args()

board = pcbnew.LoadBoard(BOARD)

# -- zone fill, per island -------------------------------------------------
islands = {}
for z in board.Zones():
    if z.GetIsRuleArea() or z.GetNetname() != "GND":
        continue
    for layer in LAYERS:
        if not z.IsOnLayer(layer):
            continue
        poly = z.GetFilledPolysList(layer)
        for i in range(poly.OutlineCount()):
            chain = poly.Outline(i)
            islands[(layer, i)] = (poly, chain, chain.BBox())

print("GND islands: %d" % len(islands))


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def inside(poly, chain, x, y):
    v = vec(x, y)
    return poly.Contains(v) and chain.PointInside(v)


def island_at(layer, x, y):
    v = vec(x, y)
    for key, (poly, chain, _bb) in islands.items():
        if key[0] != layer:
            continue
        if poly.Contains(v) and chain.PointInside(v):
            return key
    return None


# -- union-find ------------------------------------------------------------
parent = {}


def find(a):
    parent.setdefault(a, a)
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb


for key in islands:
    find(key)

vias = [t for t in board.GetTracks()
        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "GND"]
tracks = [t for t in board.GetTracks()
          if not isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "GND"]

vpos = []
for v in vias:
    s = v.GetStart()
    vpos.append((TO(s.x), TO(s.y)))

for i, v in enumerate(vias):
    n = ("V", i)
    find(n)
    x, y = vpos[i]
    for layer in LAYERS:
        k = island_at(layer, x, y)
        if k is not None:
            union(n, k)


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(px - x1, py - y1)
    u = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + u * dx), py - (y1 + u * dy))


ends = []
for t in tracks:
    a, c = t.GetStart(), t.GetEnd()
    ends.append((TO(a.x), TO(a.y), TO(c.x), TO(c.y), t.GetLayer(), TO(t.GetWidth()) / 2.0))

for i, t in enumerate(tracks):
    n = ("T", i)
    find(n)
    ax, ay, cx, cy, layer, hw = ends[i]
    for (px, py) in ((ax, ay), (cx, cy)):
        k = island_at(layer, px, py)
        if k is not None:
            union(n, k)
    for j, (vx, vy) in enumerate(vpos):
        if min(math.hypot(vx - ax, vy - ay), math.hypot(vx - cx, vy - cy)) <= hw + 0.01:
            union(n, ("V", j))
    for j, (bx, by, dx2, dy2, ol, oh) in enumerate(ends):
        if j <= i or ol != layer:
            continue
        if (seg_dist(ax, ay, bx, by, dx2, dy2) <= oh + 0.01
                or seg_dist(cx, cy, bx, by, dx2, dy2) <= oh + 0.01):
            union(n, ("T", j))

# A pad is connected to an island if its copper reaches it, and copper does not
# stop at the pad edge: a thermal-relief pad sits in a gap with spokes crossing
# it, so the pad's *centre* falls outside the fill while the pad is plainly
# joined to it.  Sampling just outside the pad outline catches those.
for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNetname() != "GND":
            continue
        o = p.GetPosition()
        x, y = TO(o.x), TO(o.y)
        n = ("P", f.GetReference(), str(p.GetNumber()))
        find(n)
        dr = p.GetDrillSize()
        thru = dr.x > 0 or dr.y > 0
        bb = p.GetBoundingBox()
        rw, rh = TO(bb.GetWidth()) / 2.0, TO(bb.GetHeight()) / 2.0
        reach = [(x, y)]
        for ux, uy in ANGLES:
            reach.append((x + (rw + 0.05) * ux, y + (rh + 0.05) * uy))
        for layer in (LAYERS if thru else (p.GetLayer(),)):
            for (qx, qy) in reach:
                k = island_at(layer, qx, qy)
                if k is not None:
                    union(n, k)

def is_island(k):
    return isinstance(k, tuple) and len(k) == 2 and k[0] in LAYERS


def tally(g):
    return (sum(1 for k in g if is_island(k)),
            sum(1 for k in g if isinstance(k, tuple) and k[0] == "V"),
            sum(1 for k in g if isinstance(k, tuple) and k[0] == "T"),
            sum(1 for k in g if isinstance(k, tuple) and k[0] == "P"))


def search(poly, chain, bb, targets):
    """Spots inside this island that are also inside one of `targets`, with the
    whole via footprint clear of the edge of both."""
    x1, y1 = TO(bb.GetLeft()), TO(bb.GetTop())
    x2, y2 = TO(bb.GetRight()), TO(bb.GetBottom())
    nx = int((x2 - x1) / STEP) + 1
    ny = int((y2 - y1) / STEP) + 1
    out = []
    for ia in range(nx):
        for ja in range(ny):
            qx = x1 + ia * STEP
            qy = y1 + ja * STEP
            if not inside(poly, chain, qx, qy):
                continue
            for kb in targets:
                bp, bc, bbb = islands[kb]
                if not (TO(bbb.GetLeft()) <= qx <= TO(bbb.GetRight())
                        and TO(bbb.GetTop()) <= qy <= TO(bbb.GetBottom())):
                    continue
                if not inside(bp, bc, qx, qy):
                    continue
                ok = True
                for ux, uy in ANGLES:
                    if not inside(poly, chain, qx + R * ux, qy + R * uy):
                        ok = False
                        break
                    if not inside(bp, bc, qx + R * ux, qy + R * uy):
                        ok = False
                        break
                if not ok:
                    continue
                if any(math.hypot(qx - vx, qy - vy) < CROWD for (vx, vy) in vpos):
                    continue
                out.append((qx, qy, kb))
                break
    return out


def diagnose(k, main_root):
    """When an island has no landing, show what is actually under it: how much
    of its opposite layer it covers, which islands those are, and the largest
    via that would fit at any of them."""
    poly, chain, bb = islands[k]
    other = B_CU if k[0] == F_CU else F_CU
    x1, y1 = TO(bb.GetLeft()), TO(bb.GetTop())
    x2, y2 = TO(bb.GetRight()), TO(bb.GetBottom())
    nx = int((x2 - x1) / STEP) + 1
    ny = int((y2 - y1) / STEP) + 1
    pts = []
    for ia in range(nx):
        for ja in range(ny):
            qx, qy = x1 + ia * STEP, y1 + ja * STEP
            if inside(poly, chain, qx, qy):
                pts.append((qx, qy))
    print("     %s: %d grid point(s) of its own copper" % (k, len(pts)))
    for j in sorted(kk for kk in islands if kk[0] == other):
        jp, jc, jbb = islands[j]
        hits = [p for p in pts
                if TO(jbb.GetLeft()) <= p[0] <= TO(jbb.GetRight())
                and TO(jbb.GetTop()) <= p[1] <= TO(jbb.GetBottom())
                and inside(jp, jc, p[0], p[1])]
        if not hits:
            continue
        if len(hits) > 300:
            stride = len(hits) // 300 + 1
            hits = hits[::stride]
        best, bestp = 0.0, None
        for r in (0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15, 0.10, 0.05):
            for (qx, qy) in hits:
                ok = True
                for ux, uy in ANGLES:
                    if not inside(poly, chain, qx + r * ux, qy + r * uy):
                        ok = False
                        break
                    if not inside(jp, jc, qx + r * ux, qy + r * uy):
                        ok = False
                        break
                if ok:
                    best, bestp = r, (qx, qy)
                    break
            if bestp:
                break
        print("     vs %-8s area=%7.2f %-6s: %4d shared point(s); widest via "
              "r=%.2f %s" % (j, abs(jc.Area()) / 1e12,
                             "MAIN" if find(j) == main_root else "orphan",
                             len(hits), best,
                             "none" if bestp is None else "at (%.2f,%.2f)" % bestp))


def components():
    groups = collections.defaultdict(list)
    for key in list(parent):
        groups[find(key)].append(key)
    return groups


# One via can only ever weld an island to the *other* layer, so an island whose
# opposite-layer copper is equally stranded has to wait for a neighbour to be
# rescued first.  Going round again after each placement is what gets that
# pair out: R6's island and the B.Cu island it shares a via with are joined to
# each other but to nothing else, and neither can be reached until R8's island
# -- which overlaps one of them -- is back on the plane.
planned = []
for rnd in range(1, 12):
    groups = components()
    main = max(groups.values(), key=lambda g: tally(g)[1])
    main_root = find(next(iter(main)))
    orphans = sorted(k for k in islands if find(k) != main_root)
    if not orphans:
        break
    print("\n-- round %d: main body has %d island(s)/%d via(s); %d orphan(s)"
          % (rnd, tally(main)[0], tally(main)[1], len(orphans)))
    for k in orphans:
        g = groups[find(k)]
        npads = [(p[1], p[2]) for p in g if isinstance(p, tuple) and p[0] == "P"]
        print("   %s area=%7.2f mm2  group: %d island(s), %d via(s), %d pad(s) %s"
              % (k, abs(islands[k][1].Area()) / 1e12,
                 tally(g)[0], tally(g)[1], tally(g)[3], npads))

    placed = None
    for k in orphans:
        poly, chain, bb = islands[k]
        other = B_CU if k[0] == F_CU else F_CU
        targets = [j for j in islands if j[0] == other and find(j) == main_root]
        if not targets:
            continue
        cands = search(poly, chain, bb, targets)
        if not cands:
            continue
        cxm = (TO(bb.GetLeft()) + TO(bb.GetRight())) / 2.0
        cym = (TO(bb.GetTop()) + TO(bb.GetBottom())) / 2.0
        bx, by, kb = min(cands, key=lambda c: math.hypot(c[0] - cxm, c[1] - cym))
        print("   -> via (%.3f, %.3f)  %s -> %s   [%d candidate(s)]"
              % (bx, by, k, kb, len(cands)))
        planned.append((bx, by))
        union(k, kb)
        vpos.append((bx, by))
        placed = True
        break
    if not placed:
        print("   !! no landing point for any remaining orphan -- geometry:")
        for k in orphans:
            diagnose(k, main_root)
        break

if not args.fix:
    print("\n(dry run -- %d via(s) planned)" % len(planned))
    raise SystemExit(0)

if not planned:
    print("\nnothing to do")
    raise SystemExit(0)

shutil.copyfile(BOARD, BAK)
print("\nbacked up -> %s" % BAK)

net = board.FindNet("GND")
kept = []
for (x, y) in planned:
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(x, y))
    v.SetWidth(pcbnew.FromMM(VIA_D))
    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    v.SetNetCode(net.GetNetCode())
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(F_CU, B_CU)
    board.Add(v)
    kept.append(v)
    print("  placed via at (%.3f, %.3f)" % (x, y))

print("refilling zones ...")
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(BOARD)
_keep_alive = kept          # hold the proxies until the save lands
print("saved")
