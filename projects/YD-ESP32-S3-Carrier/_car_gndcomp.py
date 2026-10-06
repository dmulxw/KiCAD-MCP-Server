"""Work out which GND copper actually reaches the plane.

"Is this island touching a via?" is too weak a question, and it is why three
unconnected items survived a repair pass that put a via in every island that
lacked one.  Islands, vias, pads and tracks form a graph, and an island is only
really connected if some path through that graph arrives at the main ground
body.  A pair of islands joined to each other by a via, with nothing else on
either, is still an orphan -- but each island on its own looks populated.

So: union-find over all four kinds of GND item, where an edge is copper
touching copper.

  island - via          the via's centre lies in the island's copper

  island - pad          the pad's position lies in the island's copper
  island - track        a track endpoint lies in the island's copper

  via    - track        an endpoint coincides, or the via centre lies within
                        the track's half-width of its centreline, or the via's
                        copper overlaps an endpoint

  track  - track        same layer, and one endpoint lies within the other's
                        half-width of its centreline

Two tracks whose ends merely come close do not count: the endpoint has to sit
on the other's copper, which is the same rule that settled the IO9 stub.

  python _car_gndcomp.py
"""
import collections
import math
import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
TO = pcbnew.ToMM

board = pcbnew.LoadBoard(BOARD)
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

# -- islands ---------------------------------------------------------------
islands = {}          # key -> (layer, poly, chain, bbox)
for z in board.Zones():
    if z.GetIsRuleArea() or z.GetNetname() != "GND":
        continue
    for layer in LAYERS:
        if not z.IsOnLayer(layer):
            continue
        poly = z.GetFilledPolysList(layer)
        for i in range(poly.OutlineCount()):
            islands[(layer, i)] = (layer, poly, poly.Outline(i), poly.Outline(i).BBox())

print("GND islands: %d" % len(islands))


def island_at(layer, x, y):
    v = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
    for key, (lay, poly, chain, _bb) in islands.items():
        if lay != layer:
            continue
        if poly.Contains(v) and chain.PointInside(v):
            return key
    return None


# -- nodes -----------------------------------------------------------------
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

print("GND vias: %d   GND tracks: %d" % (len(vias), len(tracks)))


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(px - x1, py - y1)
    u = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + u * dx), py - (y1 + u * dy))


for i, v in enumerate(vias):
    n = ("V", i)
    find(n)
    s = v.GetStart()
    x, y = TO(s.x), TO(s.y)
    for layer in LAYERS:
        k = island_at(layer, x, y)
        if k is not None:
            union(n, k)

for i, t in enumerate(tracks):
    n = ("T", i)
    find(n)
    layer = t.GetLayer()
    hw = TO(t.GetWidth()) / 2.0
    a, c = t.GetStart(), t.GetEnd()
    ax, ay, cx, cy = TO(a.x), TO(a.y), TO(c.x), TO(c.y)
    for (px, py) in ((ax, ay), (cx, cy)):
        k = island_at(layer, px, py)
        if k is not None:
            union(n, k)
    for j, v in enumerate(vias):
        s = v.GetStart()
        vx, vy = TO(s.x), TO(s.y)
        vr = TO(v.GetWidth(pcbnew.F_Cu)) / 2.0
        if min(math.hypot(vx - ax, vy - ay), math.hypot(vx - cx, vy - cy)) <= hw + 0.01:
            union(n, ("V", j))
        elif seg_dist(vx, vy, ax, ay, cx, cy) <= hw + vr:
            union(n, ("V", j))
    for j, o in enumerate(tracks):
        if j <= i or o.GetLayer() != layer:
            continue
        oh = TO(o.GetWidth()) / 2.0
        b, d = o.GetStart(), o.GetEnd()
        bx, by, dx2, dy2 = TO(b.x), TO(b.y), TO(d.x), TO(d.y)
        if (seg_dist(ax, ay, bx, by, dx2, dy2) <= oh + 0.01
                or seg_dist(cx, cy, bx, by, dx2, dy2) <= oh + 0.01):
            union(n, ("T", j))

for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNetname() != "GND":
            continue
        n = ("P", f.GetReference(), str(p.GetNumber()), p.GetPosition().x, p.GetPosition().y)
        find(n)
        o = p.GetPosition()
        x, y = TO(o.x), TO(o.y)
        dr = p.GetDrillSize()
        thru = dr.x > 0 or dr.y > 0
        for layer in (LAYERS if thru else (p.GetLayer(),)):
            k = island_at(layer, x, y)
            if k is not None:
                union(n, k)
        for j, v in enumerate(vias):
            s = v.GetStart()
            if math.hypot(TO(s.x) - x, TO(s.y) - y) <= 0.01:
                union(n, ("V", j))
        for j, t in enumerate(tracks):
            if not thru and t.GetLayer() != p.GetLayer():
                continue
            a, c = t.GetStart(), t.GetEnd()
            hw = TO(t.GetWidth()) / 2.0
            if seg_dist(x, y, TO(a.x), TO(a.y), TO(c.x), TO(c.y)) <= hw + 0.01:
                union(n, ("T", j))

groups = collections.defaultdict(list)
for key in list(parent):
    groups[find(key)].append(key)

def size(g):
    return sum(1 for k in g if isinstance(k, tuple) and len(k) == 2 and k[0] in LAYERS)

ranked = sorted(groups.values(), key=size, reverse=True)
print("\nGND components: %d" % len(ranked))
for gi, g in enumerate(ranked[:12]):
    isl = [k for k in g if isinstance(k, tuple) and len(k) == 2 and k[0] in LAYERS]
    nv = sum(1 for k in g if isinstance(k, tuple) and k[0] == "V")
    nt = sum(1 for k in g if isinstance(k, tuple) and k[0] == "T")
    npd = sum(1 for k in g if isinstance(k, tuple) and k[0] == "P")
    area = sum(abs(islands[k][2].Area()) / 1e12 for k in isl)
    print("  [%2d] islands=%2d vias=%3d tracks=%3d pads=%2d area=%9.2f mm2"
          % (gi, len(isl), nv, nt, npd, area))
    if gi > 0 and len(isl):
        for k in sorted(isl)[:6]:
            bb = islands[k][3]
            print("        island %s bbox=(%.2f,%.2f)-(%.2f,%.2f) area=%.3f"
                  % (k, TO(bb.GetLeft()), TO(bb.GetTop()),
                     TO(bb.GetRight()), TO(bb.GetBottom()),
                     abs(islands[k][2].Area()) / 1e12))
