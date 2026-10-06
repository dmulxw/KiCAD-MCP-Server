"""Route the last stranded ground island back to the plane.

Three islands came out of the pour with no path to the bulk of the ground, and
two of them took a via.  The third cannot: a via needs one layer to be the
island and the other to be the plane, and under this island the far layer is
its own stranded companion -- the two were cut off together.  Six grid points
of overlap with the main plane, none of them wide enough for a via pad, is the
whole of what the two layers share there.

What is left is a track, and a track is not restricted to the layer the island
is on.  The island is fenced by traces, but the fence is not solid on either
layer: the front has gaps between the traces that the pour never filled, and
the back has pockets the pour never reached.  A track that changes layer inside
those gaps can walk round a fence that neither layer is passable on alone.

So this searches both layers at once.  A state is a grid cell plus the layer,
moves are one cell along that layer, and a via is a move that changes layer at
a cell that is clear on both.  Vias are priced high enough that a route without
them wins, but low enough that one is taken when it is the only way through.
The start is any cell inside the stranded island, the goal any cell inside the
main ground on the layer the route arrives on, and the route is only accepted
if the finished polyline holds the board's own 0.30 mm width and 0.20 mm
clearance when measured against every non-ground item -- a grid is a
discretisation, and the answer has to survive the arithmetic that follows it.

  python _car_orphanroute.py             # find the route, change nothing
  python _car_orphanroute.py --fix       # lay the track, refill, save
"""
import argparse
import collections
import heapq
import math
import shutil

import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
BAK = BOARD + ".pre-orphanroute.bak"

TO = pcbnew.ToMM
FMM = pcbnew.FromMM
F_CU, B_CU = pcbnew.F_Cu, pcbnew.B_Cu
LAYERS = (F_CU, B_CU)
LNAME = {F_CU: "F.Cu", B_CU: "B.Cu"}

STEP = 0.20
TRACK_W = 0.30
CLEAR = 0.20
HW = TRACK_W / 2.0
VIA_D = 0.60
VIA_DRILL = 0.30
VIA_R = VIA_D / 2.0
VIA_COST = 8          # in grid steps: dear, but cheaper than no route at all
ANGLES = [(math.cos(a * math.pi / 4.0), math.sin(a * math.pi / 4.0)) for a in range(8)]

ap = argparse.ArgumentParser()
ap.add_argument("--fix", action="store_true", help="lay the track and vias, save")
ap.add_argument("--bbox", default="30,8,70,40", help="routing window x1,y1,x2,y2")
args = ap.parse_args()

board = pcbnew.LoadBoard(BOARD)
x0, y0, x1, y1 = [float(v) for v in args.bbox.split(",")]


def vec(x, y):
    return pcbnew.VECTOR2I(FMM(x), FMM(y))


# -- ground fill, per island ----------------------------------------------
# Keyed by (layer, outline index) because one zone holds many disjoint pieces
# and connectivity is a property of the piece, not of the zone.
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


def inside(poly, chain, x, y):
    v = vec(x, y)
    return poly.Contains(v) and chain.PointInside(v)


def inside_r(poly, chain, x, y, r):
    """The whole disc of radius r lies in this island -- what a via needs so its
    pad does not hang off the copper it is supposed to weld."""
    if not inside(poly, chain, x, y):
        return False
    for ux, uy in ANGLES:
        if not inside(poly, chain, x + r * ux, y + r * uy):
            return False
    return True


def island_at(layer, x, y):
    for key, (poly, chain, _bb) in islands.items():
        if key[0] != layer:
            continue
        if inside(poly, chain, x, y):
            return key
    return None


# -- union-find over everything carrying the ground net --------------------
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

for i, (x, y) in enumerate(vpos):
    n = ("V", i)
    find(n)
    for layer in LAYERS:
        k = island_at(layer, x, y)
        if k is not None:
            union(n, k)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


ends = []
for t in tracks:
    a, c = t.GetStart(), t.GetEnd()
    ends.append((TO(a.x), TO(a.y), TO(c.x), TO(c.y), t.GetLayer(), TO(t.GetWidth()) / 2.0))

for i, (ax, ay, cx, cy, layer, hw) in enumerate(ends):
    n = ("T", i)
    find(n)
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

# A pad joins an island when its copper reaches it, and copper does not stop at
# the pad outline: a thermal-relief pad sits in a gap with spokes crossing it,
# so the centre falls outside the fill while the pad is plainly joined.  The
# eight samples just outside the pad bbox are what catch those.
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
        for layer in (LAYERS if thru else (p.GetLayer(),)):
            for (ux, uy) in [(0, 0)] + ANGLES:
                k = island_at(layer, x + (rw + 0.05) * ux, y + (rh + 0.05) * uy)
                if k is not None:
                    union(n, k)


def is_island(k):
    return isinstance(k, tuple) and len(k) == 2 and k[0] in LAYERS


groups = collections.defaultdict(list)
for key in list(parent):
    groups[find(key)].append(key)

main = max(groups.values(),
           key=lambda g: sum(1 for k in g if isinstance(k, tuple) and k[0] == "V"))
main_root = find(next(iter(main)))
print("main body: %d island(s), %d via(s)"
      % (sum(1 for k in main if is_island(k)),
         sum(1 for k in main if isinstance(k, tuple) and k[0] == "V")))

orphans = [k for k in islands if k[0] == F_CU and find(k) != main_root]
if not orphans:
    print("\nnothing stranded on F.Cu")
    raise SystemExit(0)
orphans.sort(key=lambda k: -abs(islands[k][1].Area()))
target = orphans[0]
print("target: %s area=%.2f mm2  bbox=(%.2f,%.2f)-(%.2f,%.2f)"
      % (target, abs(islands[target][1].Area()) / 1e12,
         TO(islands[target][2].GetLeft()), TO(islands[target][2].GetTop()),
         TO(islands[target][2].GetRight()), TO(islands[target][2].GetBottom())))

goals = {L: [k for k in islands if k[0] == L and find(k) == main_root] for L in LAYERS}
for L in LAYERS:
    if goals[L]:
        print("main ground on %s: %d island(s), largest %.2f mm2"
              % (LNAME[L], len(goals[L]), max(abs(islands[k][1].Area()) / 1e12 for k in goals[L])))


# -- obstacles, per layer --------------------------------------------------
# Only non-ground copper matters: ground copper is what the track is joining.
# A via of another net blocks both layers, because its pad is on both.
obst = {F_CU: [], B_CU: []}


def add(layer, o):
    obst[layer].append(o)


for t in board.GetTracks():
    if t.GetNetname() == "GND":
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        try:
            r = TO(t.GetWidth(B_CU)) / 2.0
        except Exception:
            r = TO(t.GetWidth(F_CU)) / 2.0
        for L in LAYERS:
            add(L, ("disc", TO(s.x), TO(s.y), r, t.GetNetname()))
    else:
        a, c = t.GetStart(), t.GetEnd()
        add(t.GetLayer(), ("seg", TO(a.x), TO(a.y), TO(c.x), TO(c.y),
                           TO(t.GetWidth()) / 2.0, t.GetNetname()))

for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNetname() == "GND":
            continue
        bb = p.GetBoundingBox()
        for L in LAYERS:
            if p.IsOnLayer(L):
                add(L, ("rect", TO(bb.GetLeft()), TO(bb.GetTop()),
                        TO(bb.GetRight()), TO(bb.GetBottom()), p.GetNetname()))

for z in board.Zones():
    if z.GetIsRuleArea() or z.GetNetname() == "GND":
        continue
    bb = z.GetBoundingBox()
    for L in LAYERS:
        if z.IsOnLayer(L):
            add(L, ("rect", TO(bb.GetLeft()), TO(bb.GetTop()),
                    TO(bb.GetRight()), TO(bb.GetBottom()), z.GetNetname()))

for L in LAYERS:
    print("non-ground %s obstacles: %d" % (LNAME[L], len(obst[L])))


def surf_dist(x, y, o):
    """Distance from a point to an obstacle's nearest copper edge, 0 inside."""
    if o[0] == "seg":
        _, ax, ay, bx, by, hw, _n = o
        return max(0.0, seg_dist(x, y, ax, ay, bx, by) - hw)
    if o[0] == "disc":
        _, cx, cy, r, _n = o
        return max(0.0, math.hypot(x - cx, y - cy) - r)
    _, l, t, r, b, _n = o
    return math.hypot(max(l - x, 0.0, x - r), max(t - y, 0.0, y - b))


def segs_cross(ax, ay, bx, by, cx, cy, dx, dy):
    def o(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    d1, d2 = o(cx, cy, dx, dy, ax, ay), o(cx, cy, dx, dy, bx, by)
    d3, d4 = o(ax, ay, bx, by, cx, cy), o(ax, ay, bx, by, dx, dy)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def seg_surf_dist(ax, ay, bx, by, o):
    """Distance from a segment to an obstacle's edge, 0 if they touch."""
    if o[0] == "seg":
        _, cx, cy, dx, dy, hw, _n = o
        if segs_cross(ax, ay, bx, by, cx, cy, dx, dy):
            return 0.0
        return max(0.0, min(seg_dist(cx, cy, ax, ay, bx, by),
                           seg_dist(dx, dy, ax, ay, bx, by),
                           seg_dist(ax, ay, cx, cy, dx, dy),
                           seg_dist(bx, by, cx, cy, dx, dy)) - hw)
    if o[0] == "disc":
        _, cx, cy, r, _n = o
        return max(0.0, seg_dist(cx, cy, ax, ay, bx, by) - r)
    _, l, t, r, b, _n = o
    n = max(2, int(math.hypot(bx - ax, by - ay) / 0.05) + 1)
    best = 1e9
    for k in range(n + 1):
        u = k / float(n)
        best = min(best, surf_dist(ax + (bx - ax) * u, ay + (by - ay) * u, o))
    return best


# -- the grid --------------------------------------------------------------
# Four maps, because a via pad is wider than the track, and each is per layer.
nx = int((x1 - x0) / STEP) + 1
ny = int((y1 - y0) / STEP) + 1
N = nx * ny
gtrk = {L: bytearray(N) for L in LAYERS}
gvia = {L: bytearray(N) for L in LAYERS}

try:
    eb = board.GetBoardEdgesBoundingBox()
    edge = (TO(eb.GetLeft()) + 1.0, TO(eb.GetTop()) + 1.0,
            TO(eb.GetRight()) - 1.0, TO(eb.GetBottom()) - 1.0)
except Exception:
    edge = None


def cellx(i):
    return x0 + i * STEP


def celly(j):
    return y0 + j * STEP


for L in LAYERS:
    for j in range(ny):
        cy = celly(j)
        for i in range(nx):
            cx = cellx(i)
            if edge and not (edge[0] <= cx <= edge[2] and edge[1] <= cy <= edge[3]):
                gtrk[L][j * nx + i] = 1
                gvia[L][j * nx + i] = 1

for L in LAYERS:
    for o in obst[L]:
        if o[0] == "seg":
            _, ax, ay, bx, by, hw, _n = o
            l, t = min(ax, bx) - hw, min(ay, by) - hw
            r, b = max(ax, bx) + hw, max(ay, by) + hw
        elif o[0] == "disc":
            _, cx, cy, rad, _n = o
            l, t, r, b = cx - rad, cy - rad, cx + rad, cy + rad
        else:
            _, l, t, r, b, _n = o
        for rad, grid in ((HW + CLEAR, gtrk[L]), (VIA_R + CLEAR, gvia[L])):
            i0 = max(0, int(math.floor((l - rad - x0) / STEP)))
            i1 = min(nx - 1, int(math.ceil((r + rad - x0) / STEP)))
            j0 = max(0, int(math.floor((t - rad - y0) / STEP)))
            j1 = min(ny - 1, int(math.ceil((b + rad - y0) / STEP)))
            for j in range(j0, j1 + 1):
                cy = celly(j)
                for i in range(i0, i1 + 1):
                    n = j * nx + i
                    if grid[n]:
                        continue
                    if surf_dist(cellx(i), cy, o) < rad:
                        grid[n] = 1

tpoly, tchain, _tbb = islands[target]
starts = []
for j in range(ny):
    for i in range(nx):
        n = j * nx + i
        if not gtrk[F_CU][n] and inside(tpoly, tchain, cellx(i), celly(j)):
            starts.append((n, F_CU))
print("start cells inside the stranded island: %d" % len(starts))

goal = set()
for L in LAYERS:
    for k in goals[L]:
        gpoly, gchain, gbb = islands[k]
        l, t = TO(gbb.GetLeft()) - 0.1, TO(gbb.GetTop()) - 0.1
        r, b = TO(gbb.GetRight()) + 0.1, TO(gbb.GetBottom()) + 0.1
        i0 = max(0, int(math.floor((l - x0) / STEP)))
        i1 = min(nx - 1, int(math.ceil((r - x0) / STEP)))
        j0 = max(0, int(math.floor((t - y0) / STEP)))
        j1 = min(ny - 1, int(math.ceil((b - y0) / STEP)))
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                n = j * nx + i
                if not gtrk[L][n] and inside(gpoly, gchain, cellx(i), celly(j)):
                    goal.add((n, L))
print("goal cells on the main ground: %d" % len(goal))

# -- Dijkstra over (cell, layer) ------------------------------------------
NB = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
INF = float("inf")
dist = {}
prev = {}
heap = []
for (n, L) in starts:
    dist[(n, L)] = 0
    prev[(n, L)] = None
    heapq.heappush(heap, (0, n, L))

found = None
while heap:
    d, n, L = heapq.heappop(heap)
    if d > dist.get((n, L), INF):
        continue
    if (n, L) in goal:
        found = (n, L)
        break
    i, j = n % nx, n // nx
    for di, dj in NB:
        ni, nj = i + di, j + dj
        if not (0 <= ni < nx and 0 <= nj < ny):
            continue
        m = nj * nx + ni
        if gtrk[L][m]:
            continue
        if di and dj and (gtrk[L][j * nx + ni] or gtrk[L][nj * nx + i]):
            continue          # do not squeeze diagonally between two blocked cells
        nd = d + (1.4142 if (di and dj) else 1.0)
        if nd < dist.get((m, L), INF):
            dist[(m, L)] = nd
            prev[(m, L)] = (n, L)
            heapq.heappush(heap, (nd, m, L))
    other = B_CU if L == F_CU else F_CU
    if not gvia[L][n] and not gvia[other][n]:
        nd = d + VIA_COST
        if nd < dist.get((n, other), INF):
            dist[(n, other)] = nd
            prev[(n, other)] = (n, L)
            heapq.heappush(heap, (nd, n, other))

if found is None:
    print("\nno route: %d state(s) explored, no goal reached" % len(dist))
    print("   '#' explored   'o' main ground   '+' island   '.' blocked, front layer")
    for L in LAYERS:
        g = goal_cells = {n for (n, LL) in goal if LL == L}
        print("\n-- %s --" % LNAME[L])
        for j in range(ny):
            row = []
            for i in range(nx):
                m = j * nx + i
                if (m, L) in dist:
                    row.append("#")
                elif m in goal_cells:
                    row.append("o")
                elif not gtrk[L][m]:
                    row.append(" ")
                elif inside(tpoly, tchain, cellx(i), celly(j)):
                    row.append("+")
                else:
                    row.append(".")
            print("%6.2f %s" % (celly(j), "".join(row)))
    raise SystemExit(1)

# Collapse to distinct (cell, layer) runs.
seq = []
cur = found
while cur is not None:
    seq.append(cur)
    cur = prev[cur]
seq.reverse()
runs = []
for (n, L) in seq:
    p = (cellx(n % nx), celly(n // nx))
    if runs and runs[-1][0] == L:
        runs[-1][1].append(p)
    else:
        runs.append([L, [p]])

print("\nroute: %d layer run(s), %d via(s)" % (len(runs), len(runs) - 1))
for L, pts in runs:
    print("   %s: %d grid point(s)" % (LNAME[L], len(pts)))


def cell_of(x, y):
    i = int(round((x - x0) / STEP))
    j = int(round((y - y0) / STEP))
    if 0 <= i < nx and 0 <= j < ny:
        return j * nx + i
    return -1


def clear_line(L, ax, ay, bx, by):
    n = max(2, int(math.hypot(bx - ax, by - ay) / (STEP * 0.5)) + 1)
    for k in range(n + 1):
        u = k / float(n)
        c = cell_of(ax + (bx - ax) * u, ay + (by - ay) * u)
        if c < 0 or gtrk[L][c]:
            return False
    return True


# Straighten each run: from a vertex reach as far ahead as the grid still
# allows, so the track keeps a channel's own diagonal instead of zig-zagging.
for r in runs:
    L, pts = r
    if len(pts) < 3:
        continue
    clean = [pts[0]]
    a = 0
    while a < len(pts) - 1:
        b, far = a + 1, a + 1
        while b < len(pts) and clear_line(L, pts[a][0], pts[a][1], pts[b][0], pts[b][1]):
            far = b
            b += 1
        clean.append(pts[far])
        a = far
    r[1] = clean

for L, pts in runs:
    print("   %s: %d vertex/vertices" % (LNAME[L], len(pts)))

via_pts = [runs[k][1][-1] for k in range(len(runs) - 1)]

# -- verify against real geometry, not the grid ----------------------------
worst = (1e9, None, None)
for L, pts in runs:
    for k in range(len(pts) - 1):
        for o in obst[L]:
            d = seg_surf_dist(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1], o) - HW
            if d < worst[0]:
                worst = (d, o[-1], LNAME[L])
worst_via = (1e9, None, None)
for (x, y) in via_pts:
    for L in LAYERS:
        for o in obst[L]:
            d = surf_dist(x, y, o) - VIA_R
            if d < worst_via[0]:
                worst_via = (d, o[-1], LNAME[L])

print("\ntrack clearance margin: %+.3f mm (worst: %s on %s)" % worst)
print("via   clearance margin: %+.3f mm (worst: %s on %s)" % worst_via)
print("required: %.3f mm" % CLEAR)
if worst[0] < CLEAR - 1e-6 or worst_via[0] < CLEAR - 1e-6:
    print("\n!! the route does not hold clearance -- refusing to lay it")
    raise SystemExit(1)

for L, pts in runs:
    for k in range(len(pts) - 1):
        print("   %s (%.3f,%.3f) -> (%.3f,%.3f)  %.2f mm"
              % (LNAME[L], pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1],
                 math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])))
for (x, y) in via_pts:
    print("   via (%.3f, %.3f)" % (x, y))

print("\nwhat each end welds to:")
for (x, y) in [runs[0][1][0]] + via_pts + [runs[-1][1][-1]]:
    for L in LAYERS:
        k = island_at(L, x, y)
        tag = "" if k is None else ("  MAIN" if find(k) == main_root else "  ORPHAN")
        print("   (%.3f, %.3f) %s -> %s%s" % (x, y, LNAME[L], k, tag))

if not args.fix:
    print("\n(dry run -- nothing written)")
    raise SystemExit(0)

shutil.copyfile(BOARD, BAK)
print("\nbacked up -> %s" % BAK)

net = board.FindNet("GND")
kept = []
for (x, y) in via_pts:
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(x, y))
    v.SetWidth(FMM(VIA_D))
    v.SetDrill(FMM(VIA_DRILL))
    v.SetNetCode(net.GetNetCode())
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(F_CU, B_CU)
    board.Add(v)
    kept.append(v)
    print("  via at (%.3f, %.3f)" % (x, y))

for L, pts in runs:
    for k in range(len(pts) - 1):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(vec(pts[k][0], pts[k][1]))
        t.SetEnd(vec(pts[k + 1][0], pts[k + 1][1]))
        t.SetWidth(FMM(TRACK_W))
        t.SetLayer(L)
        t.SetNetCode(net.GetNetCode())
        board.Add(t)
        kept.append(t)

print("refilling zones ...")
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(BOARD)
_keep_alive = kept          # hold the proxies until the save lands
print("saved")
