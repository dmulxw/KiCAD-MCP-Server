"""Join a many-island net into one, one island at a time.

route-open-carrier.py routes a pad to the nearest piece of the same net's
copper.  That is the entire job for a two-pad net (595 output -> header pin)
and it is nowhere near enough for +3V3, which is 24 separate islands: one pass
merges exactly two of them and the run ends with 23 still to do.  Running it
again does not help either -- it picks the same start pad every time, and by
then that pad is joined to something, so the next pass finds a goal one cell
away and stops.

This drives the same A* repeatedly instead: find the islands, pick the one
that is cheapest to reach, aim at everything outside it, emit, and do it again
until a single island is left.  It shares the router's geometry, its legality
grid and its emitter, so what it lays down is exactly what the router would
have laid down given a two-island net.

The grid is built once, not per pass.  A pass only ever adds copper on its own
net, and the router's obstacle set is each item that is *not* on that net, so
the field the search sees is bit-identical on every pass; rebuilding it would
be the entire cost of the run for none of the effect.

  python _join.py NET [--board PATH] [--step 0.1] [--safety 0.03]
                      [--via-cost 25.0] [--max N] [--dry-run] [--lock]
"""
import importlib.util
import sys

import pcbnew

spec = importlib.util.spec_from_file_location(
    "roc", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
           r"\scripts\route-open-carrier.py")
roc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roc)
S = roc.S

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
NET = None
STEP = 0.1
CLEAR = 0.16
SAFETY = 0.03
VIA_COST = 25.0
MAX = 60
DRY = False
LOCK = False
#: REF.PAD to leave from on the first pass, instead of letting the driver pick
#: the cheapest island.  This is a probe as much as an option: aiming a named
#: island at the rest answers "can these two halves ever meet?" without
#: committing any copper, which is the question a long-haul power link has to
#: settle before anything is routed through the space it would need.
FORCED = None

#: Two pieces of copper this close or closer are one island.  Routes end on
#: pad copper and on other routes' copper exactly, so the test only has to
#: absorb the 1nm rounding in VECTOR2I, not a real gap.
TOL = 0.02

argv = sys.argv[1:]
k = 0
while k < len(argv):
    a = argv[k]
    if a == "--board":
        BOARD = argv[k + 1]
        k += 2
    elif a == "--step":
        STEP = float(argv[k + 1])
        k += 2
    elif a == "--safety":
        SAFETY = float(argv[k + 1])
        k += 2
    elif a == "--via-cost":
        VIA_COST = float(argv[k + 1])
        k += 2
    elif a == "--max":
        MAX = int(argv[k + 1])
        k += 2
    elif a == "--from":
        FORCED = argv[k + 1]
        k += 2
    elif a == "--dry-run":
        DRY = True
        MAX = 1
        k += 1
    elif a == "--lock":
        LOCK = True
        k += 1
    elif a.startswith("--"):
        sys.exit("unknown option %s" % a)
    else:
        NET = a
        k += 1
if NET is None:
    sys.exit("usage: _join.py NET [--board PATH] ... (NET like +3V3)")

layers = [pcbnew.F_Cu, pcbnew.B_Cu]


# ---------------------------------------------------------------- island shape
def is_via(it):
    return isinstance(it, pcbnew.PCB_VIA)


def endpoints(it):
    """The points where this item can touch another.

    A track is a segment, and it meets the world at its two ends.  A pad or a
    via has no ends, so its centre stands in -- a route that arrives at a pad
    covers its centre, and one that passes over it without stopping does not
    count as a connection, which is the answer we want.
    """
    if isinstance(it, pcbnew.PCB_TRACK) and not is_via(it):
        s, e = it.GetStart(), it.GetEnd()
        return [(s.x / S, s.y / S), (e.x / S, e.y / S)]
    c = it.GetPosition()
    return [(c.x / S, c.y / S)]


def layers_of(it):
    """Layers this item is on, or None for 'all of them'.

    A via is the None case: it is the whole point of a via.  A PTH pad comes
    back as both copper layers, which is just as good.
    """
    if is_via(it):
        return None
    if isinstance(it, pcbnew.PAD):
        on = [l for l in layers if it.IsOnLayer(l)]
        return on or None
    return [it.GetLayer()]


def owner(it):
    """Reference designator of the footprint a pad belongs to, else a label."""
    if isinstance(it, pcbnew.PAD):
        fp = it.GetParent()
        if fp is not None:
            return str(fp.GetReference())
    return "?"


def compatible(la, lb):
    if la is None or lb is None:
        return True
    return any(l in lb for l in la)


def islands(items, shapes):
    """Group the net's copper into electrically separate islands."""
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    eps = [endpoints(it) for it in items]
    lays = [layers_of(it) for it in items]
    for i in range(n):
        ai, bi = shapes[i][0], shapes[i][2]
        ci, di = shapes[i][1], shapes[i][3]
        for j in range(i + 1, n):
            # Cheap reject first: the contact test is a square root each way
            # and this pair cannot be touching if even the padding does not.
            pad = TOL + 8.0
            if (shapes[j][0] - pad > bi or shapes[j][2] + pad < ai
                    or shapes[j][1] - pad > di or shapes[j][3] + pad < ci):
                continue
            if not compatible(lays[i], lays[j]):
                continue
            hit = False
            for x, y in eps[i]:
                if roc.dist_item(x, y, shapes[j]) <= TOL:
                    hit = True
                    break
            if not hit:
                for x, y in eps[j]:
                    if roc.dist_item(x, y, shapes[i]) <= TOL:
                        hit = True
                        break
            if hit:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def gap_between(g1, g2, shapes):
    """Cheapest straight-line gap between two islands, in mm.

    Advisory only -- it picks which island to join next, and a route that has
    to go the long way round a switch still beats starting from the far side
    of the board.
    """
    best = 1e9
    for i in g1:
        ax, ay, bx, by = shapes[i][:4]
        cx, cy = (ax + bx) / 2, (ay + by) / 2
        for j in g2:
            d = roc.dist_item(cx, cy, shapes[j])
            if d < best:
                best = d
            ax2, ay2, bx2, by2 = shapes[j][:4]
            d = roc.dist_item((ax2 + bx2) / 2, (ay2 + by2) / 2, shapes[i])
            if d < best:
                best = d
    return best


# ------------------------------------------------------------------- the board
board = pcbnew.LoadBoard(BOARD)
ds = board.GetDesignSettings()
edge_clear = ds.m_CopperEdgeClearance / S
print("board %s" % BOARD.rsplit("\\", 1)[-1])
print("net %s   edge clearance rule %.2f mm   safety %.2f" %
      (NET, edge_clear, SAFETY))

keep = CLEAR + roc.TRACK_W / 2 + SAFETY
pad_keep = CLEAR + roc.VIA_DIA / 2 + SAFETY
edge_keep = edge_clear + roc.TRACK_W / 2 + SAFETY
via_edge_keep = edge_clear + roc.VIA_DIA / 2 + SAFETY

items = [it for it in roc.net_items(board, NET) if roc.item_shape(it) is not None]
if not items:
    sys.exit("net %s has no copper on this board" % NET)

others = [it for it in board.GetTracks() if it.GetNetname() != NET]
for fp in board.GetFootprints():
    others.extend(p for p in fp.Pads() if p.GetNetname() != NET)

print("stamping %d other-net item(s); %d own item(s)" % (len(others), len(items)))
grid = roc.Grid(board, STEP, keep, edge_keep, pad_keep, via_edge_keep)
grid.build(layers, others)
netinfo = board.FindNet(NET)


def start_cells(it):
    """The open cells on this item, which is where a route may leave it."""
    if isinstance(it, pcbnew.PAD) and not is_via(it):
        bb = it.GetBoundingBox()
        box = (bb.GetLeft() / S, bb.GetTop() / S,
               bb.GetRight() / S, bb.GetBottom() / S)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    else:
        box = None
        cx, cy = endpoints(it)[0]
    lay = (layers_of(it) or [pcbnew.F_Cu])[0]
    si, sj = grid.ij(cx, cy)
    out = []
    for di in range(-4, 5):
        for dj in range(-4, 5):
            i, j = si + di, sj + dj
            if not (0 <= i < grid.nx and 0 <= j < grid.ny):
                continue
            x, y = grid.xy(i, j)
            if box is None or (box[0] <= x <= box[2] and box[1] <= y <= box[3]):
                out.append((lay, i, j))
    if not out:
        out = [(lay, si, sj)]
    return out


def goal_cells(sel):
    out = set()
    for i in sel:
        ax, ay, bx, by = shapes[i][:4]
        cx, cy = (ax + bx) / 2, (ay + by) / 2
        gi, gj = grid.ij(cx, cy)
        if not (0 <= gi < grid.nx and 0 <= gj < grid.ny):
            continue
        for l in (layers_of(items[i]) or layers):
            out.add((l, gi, gj))
    return out


def emit(path):
    runs = roc.layer_runs(path)
    tracks = []
    for run in runs:
        tracks.extend(roc.merge_run(run))
    # The search changes layer in single-cell steps, so an obstacle it cannot
    # pass shows up as F->B->F->B within a few tenths of a millimetre; one via
    # covers that whole cluster (it is 0.6mm across) as in the router.
    vias = []
    for k in range(1, len(runs)):
        c = runs[k][0]
        x, y = grid.xy(c[1], c[2])
        if any((x - vx) ** 2 + (y - vy) ** 2 < roc.VIA_DIA ** 2 for vx, vy in vias):
            continue
        vias.append((x, y))
    added = []
    for x, y in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(x * S), int(y * S)))
        v.SetWidth(int(roc.VIA_DIA * S))
        v.SetDrill(int(0.3 * S))
        v.SetNet(netinfo)
        v.SetLocked(LOCK)
        board.Add(v)
        added.append(v)
    for layer, i0, j0, i1, j1 in tracks:
        if i0 == i1 and j0 == j1:
            continue
        x0, y0 = grid.xy(i0, j0)
        x1, y1 = grid.xy(i1, j1)
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(x0 * S), int(y0 * S)))
        t.SetEnd(pcbnew.VECTOR2I(int(x1 * S), int(y1 * S)))
        t.SetWidth(int(roc.TRACK_W * S))
        t.SetLayer(layer)
        t.SetNet(netinfo)
        t.SetLocked(LOCK)
        board.Add(t)
        added.append(t)
    return added, tracks, vias


# ------------------------------------------------------------------- the loop
shapes = [roc.item_shape(it) for it in items]
isl = islands(items, shapes)
print("\n%d island(s) to begin with" % len(isl))
if len(isl) > 1:
    sizes = sorted(len(g) for g in isl)
    print("   sizes: %s" % " ".join(str(v) for v in sizes))

dead = set()          # islands already proved to have no legal route out
for step in range(1, MAX + 1):
    live = [g for g in isl if not all(i in dead for i in g)]
    if len(live) <= 1:
        break

    # Join the cheapest reachable island rather than the biggest or the
    # smallest: a one-pad island in a crowded corner is cheap by size and
    # expensive in fact, and this is the measurement that tells them apart.
    pick = min(live, key=lambda g: gap_between(g, [i for i in range(len(items))
                                                   if i not in g], shapes))
    forced_idx = None
    if step == 1 and FORCED:
        ref, _, num = FORCED.rpartition(".")
        for i, it in enumerate(items):
            if (isinstance(it, pcbnew.PAD) and owner(it) == ref
                    and str(it.GetNumber()) == num):
                forced_idx = i
                break
        if forced_idx is None:
            sys.exit("--from %s: no such pad on net %s" % (FORCED, NET))
        # The whole island, not just the pad: aiming at the rest of the net
        # from one pad on an island that is already joined is a one-cell path.
        pick = next(g for g in isl if forced_idx in g)
        print("forced start: %s, on an island of %d item(s)" % (FORCED, len(pick)))
    rest = [i for i in range(len(items)) if i not in pick]

    if forced_idx is not None:
        origin = items[forced_idx]
    else:
        pads = [i for i in pick if isinstance(items[i], pcbnew.PAD)]
        origin = items[pads[0]] if pads else items[pick[0]]
    ax, ay = endpoints(origin)[0]
    print("\n[%d/%d] island of %d item(s), leaving from %s at (%.2f, %.2f)"
          % (step, len(isl) - 1, len(pick),
             owner(origin) if isinstance(origin, pcbnew.PAD) else "a track",
             ax, ay))

    goals = goal_cells(rest)
    if not goals:
        print("   nothing to aim at")
        break
    path = roc.astar_dual(grid, layers, start_cells(origin), goals, VIA_COST)
    if path is None:
        print("   NO PATH -- marking this island unroutable for now")
        dead.update(pick)
        continue

    nvia = sum(1 for k in range(1, len(path)) if path[k][0] != path[k - 1][0])
    length = 0.0
    for k in range(1, len(path)):
        if path[k][0] == path[k - 1][0]:
            dx = path[k][1] - path[k - 1][1]
            dy = path[k][2] - path[k - 1][2]
            length += (dx * dx + dy * dy) ** 0.5 * STEP
    print("   path %d cells, %.1f mm, %d via(s)" % (len(path), length, nvia))

    if DRY:
        print("   dry run -- not emitting")
        break

    added, tracks, vias = emit(path)
    items.extend(added)
    shapes.extend([roc.item_shape(it) for it in added])
    was = len(isl)
    isl = islands(items, shapes)
    print("   %d track(s), %d via(s) -> %d island(s)%s"
          % (len(tracks), len(vias), len(isl),
             "" if len(isl) < was else "   (NO PROGRESS -- stopping)"))
    if len(isl) >= was:
        break

print("\n%d island(s) left" % len(isl))
if not DRY:
    board.BuildConnectivity()
    pcbnew.SaveBoard(BOARD, board)
    print("saved %s" % BOARD)
