"""Route the nets an autorouter left open, with A* over a clearance map.

Freerouting converged on this board with two of 253 nets unrouted -- ROW3 and
ROW5 -- and re-running it does not help: ``-is``/``-us`` only steer the
*optimiser*, not the autorouter, so every attempt rebuilds the identical
solution. The board is not actually at its limit, but the free copper is down
to a couple of board-edge corridors, which is a planning problem rather than
one more passes setting can fix.

So this does the part the autorouter gave up on. It rasterises every other-net
item on each copper layer into a distance map, marks the cells a 0.2mm track
(or a 0.6mm via) may legally occupy, and A*s from the open pad to the nearest
piece of its own net. Board-edge clearance comes from the project's own
``min_copper_edge_clearance``.

    python route-open-nets.py <board> [--nets ROW3 ROW5] [--lock] [--dry-run]

With no ``--nets`` it routes every net that KiCad reports as split.
"""

import argparse
import heapq
import sys
from array import array

import pcbnew

S = 1e6
TRACK_W = 0.2
VIA_DIA = 0.6
INF = 1e9


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------


def item_shape(item):
    """One piece of copper as (x0, y0, x1, y1, r, box), in mm.

    ``box`` distinguishes a filled axis-aligned rectangle from a segment of
    radius ``r``. Pads come back as boxes: a pad *is* its bounding box, so
    running one through the segment distance measures the gap to the box
    diagonal instead -- which leaves most of a 5mm touch pad reading as free
    copper, and a route that drives straight through it.
    """
    if isinstance(item, pcbnew.PAD):
        bb = item.GetBoundingBox()
        return (bb.GetLeft() / S, bb.GetTop() / S,
                bb.GetRight() / S, bb.GetBottom() / S, 0.0, True)
    if isinstance(item, pcbnew.PCB_VIA):
        p = item.GetPosition()
        r = item.GetWidth() / S / 2
        return (p.x / S - r, p.y / S - r, p.x / S + r, p.y / S + r, 0.0, True)
    if isinstance(item, pcbnew.PCB_TRACK):
        s, e = item.GetStart(), item.GetEnd()
        return (min(s.x, e.x) / S, min(s.y, e.y) / S,
                max(s.x, e.x) / S, max(s.y, e.y) / S,
                item.GetWidth() / S / 2, False)
    return None


def dist_seg(px, py, ax, ay, bx, by):
    if ax == bx and ay == by:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def dist_box(px, py, ax, ay, bx, by):
    dx = max(ax - px, 0.0, px - bx)
    dy = max(ay - py, 0.0, py - by)
    return (dx * dx + dy * dy) ** 0.5


def dist_item(px, py, shape):
    """Distance from a point to one piece of copper, in mm."""
    ax, ay, bx, by, r, box = shape
    if box:
        return dist_box(px, py, ax, ay, bx, by)
    return dist_seg(px, py, ax, ay, bx, by) - r


def on_layer(item, layer):
    if isinstance(item, pcbnew.PAD):
        return item.IsOnLayer(layer)
    if isinstance(item, pcbnew.PCB_VIA):
        return True
    if isinstance(item, pcbnew.PCB_TRACK):
        return item.IsOnLayer(layer)
    return False


def netname(item):
    return item.GetNetname()


# --------------------------------------------------------------------------
# grid
# --------------------------------------------------------------------------


class Grid:
    """Distance-to-other-net-copper for one net, on both copper layers."""

    def __init__(self, board, step, keep, edge_keep, pad_keep, via_edge_keep):
        self.step = step
        self.keep = keep
        self.edge_keep = edge_keep
        self.pad_keep = pad_keep
        self.via_edge_keep = via_edge_keep
        bb = board.GetBoardEdgesBoundingBox()
        # Two different reaches: how far a stamp spreads (must cover every
        # cell whose distance could matter) and how far the grid extends past
        # the outline (nothing outside it can ever be legal, so keep it tight
        # -- at a 0.1mm step every wasted mm is ~15000 cells).
        self.stamp = max(keep, edge_keep, pad_keep) + 0.5
        pad = 0.5
        self.x0 = bb.GetLeft() / S - pad
        self.y0 = bb.GetTop() / S - pad
        self.x1 = bb.GetRight() / S + pad
        self.y1 = bb.GetBottom() / S + pad
        self.nx = int((self.x1 - self.x0) / step) + 1
        self.ny = int((self.y1 - self.y0) / step) + 1
        self.bb = (bb.GetLeft() / S, bb.GetTop() / S,
                   bb.GetRight() / S, bb.GetBottom() / S)
        self.maps = {}
        self.owners = {}

    def n(self):
        return self.nx * self.ny

    def xy(self, i, j):
        return self.x0 + i * self.step, self.y0 + j * self.step

    def ij(self, x, y):
        return (int(round((x - self.x0) / self.step)),
                int(round((y - self.y0) / self.step)))

    def build(self, layers, stamp_items):
        """Distance maps for `layers`; `stamp_items` are the obstacles."""
        for lay in layers:
            m = array("f", bytes(4 * self.n()))
            own = array("i", bytes(4 * self.n()))
            for k in range(len(m)):
                m[k] = INF
                own[k] = -1
            self.maps[lay] = m
            self.owners[lay] = own
            for item_no, it in enumerate(stamp_items):
                if not on_layer(it, lay):
                    continue
                shape = item_shape(it)
                if shape is None:
                    continue
                ax, ay, bx, by, r, box = shape
                reach = self.stamp if box else r + self.stamp
                i0 = max(0, int((ax - reach - self.x0) / self.step))
                i1 = min(self.nx - 1, int((bx + reach - self.x0) / self.step) + 1)
                j0 = max(0, int((ay - reach - self.y0) / self.step))
                j1 = min(self.ny - 1, int((by + reach - self.y0) / self.step) + 1)
                for i in range(i0, i1 + 1):
                    px = self.x0 + i * self.step
                    base = i * self.ny
                    for j in range(j0, j1 + 1):
                        k = base + j
                        if m[k] <= 0.0:
                            continue
                        d = dist_item(px, self.y0 + j * self.step, shape)
                        if d < m[k]:
                            m[k] = d
                            own[k] = item_no

    def edge_gap(self, i, j):
        """Distance from a cell to the board outline (rectangle)."""
        x, y = self.xy(i, j)
        bx0, by0, bx1, by1 = self.bb
        return min(x - bx0, bx1 - x, y - by0, by1 - y)

    def cell(self, layer, i, j):
        """(distance to nearest other-net copper, index of that item)."""
        k = i * self.ny + j
        return self.maps[layer][k], self.owners[layer][k]

    def track_ok(self, layer, i, j):
        if self.maps[layer][i * self.ny + j] < self.keep:
            return False
        return self.edge_gap(i, j) >= self.edge_keep

    def via_ok(self, i, j):
        k = i * self.ny + j
        for m in self.maps.values():
            if m[k] < self.pad_keep:
                return False
        return self.edge_gap(i, j) >= self.via_edge_keep


# --------------------------------------------------------------------------
# islands
# --------------------------------------------------------------------------


def net_items(board, name):
    out = []
    for t in board.GetTracks():
        if t.GetNetname() == name:
            out.append(t)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == name:
                out.append(pad)
    return out


def start_pad(board, ref, num):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            for pad in fp.Pads():
                if pad.GetNumber() == num:
                    return pad
    return None


# --------------------------------------------------------------------------
# A*
# --------------------------------------------------------------------------


def astar_dual(grid, layers, start_cells, goals, via_cost,
               conflict=False):
    """A* over (layer, x, y) with layer changes costing `via_cost`.

    ``goals`` is the set of target cells; it also supplies the heuristic, so a
    plain Dijkstra is not an option -- on an open board the frontier would
    balloon into a disc thousands of cells wide.
    """
    ny = grid.ny
    li = {lay: k for k, lay in enumerate(layers)}
    total = grid.n() * len(layers)
    # float64, not float32: the heap holds f = g + h, and the cheapest-entry
    # test below compares that float64 against the stored g. At float32 the
    # round-trip loses up to g * 6e-8, which is 1e-4 by the time g reaches a
    # few thousand -- far more than the 1e-6 slack, so the test starts
    # rejecting live entries and the cells they carry are never expanded.
    g = array("d", bytes(8 * total))
    for k in range(total):
        g[k] = INF
    parent = array("i", bytes(4 * total))
    for k in range(total):
        parent[k] = -1

    def idx(layer, i, j):
        return li[layer] * grid.n() + i * ny + j

    def h_to_goal(i, j):
        """Octile distance to the nearest goal cell, in step units.

        Admissible: it under-counts layer changes (which never make a route
        shorter) and matches the 1 / sqrt(2) edge costs exactly.
        """
        best = INF
        for _, gi, gj in goals:
            di = abs(i - gi)
            dj = abs(j - gj)
            d = (max(di, dj) + 0.41421356 * min(di, dj))
            if d < best:
                best = d
        return best

    heap = []
    counter = 0
    for layer, i, j in start_cells:
        k = idx(layer, i, j)
        g[k] = 0.0
        heapq.heappush(heap, (h_to_goal(i, j), counter, k))
        counter += 1

    NB = ((1, 0), (-1, 0), (0, 1), (0, -1),
          (1, 1), (1, -1), (-1, 1), (-1, -1))

    goal_k = None
    expanded = seen = 0
    #: How close the search ever got, in octile steps. On a failure this is the
    #: whole answer to "is the net sealed, or did the search just run out of
    #: board?" -- a closest approach of one or two cells means one more shape
    #: stands in the way, a hundred means the two halves are in separate rooms.
    closest = (INF, None, None)
    while heap:
        f, _, k = heapq.heappop(heap)
        lay_i, rem = divmod(k, grid.n())
        layer = layers[lay_i]
        i, j = divmod(rem, ny)
        if f > g[k] + h_to_goal(i, j) + 1e-6:
            continue
        expanded += 1

        if (layer, i, j) in goals:
            goal_k = k
            break

        d = h_to_goal(i, j)
        if d < closest[0]:
            closest = (d, (layer, i, j), k)

        # step within the layer
        for di, dj in NB:
            ni, nj = i + di, j + dj
            if ni < 0 or nj < 0 or ni >= grid.nx or nj >= grid.ny:
                continue
            extra = 0.0
            if not grid.track_ok(layer, ni, nj):
                if not conflict:
                    continue
                d, _ = grid.cell(layer, ni, nj)
                if d < 0.0:
                    continue  # inside another net's copper: a short, not a squeeze
                extra = (grid.keep - d) * 2000.0
            if di and dj:
                if not grid.track_ok(layer, i + di, j):
                    continue
                if not grid.track_ok(layer, i, j + dj):
                    continue
            nk = idx(layer, ni, nj)
            ng = g[k] + extra + (1.0 if (di == 0 or dj == 0) else 1.41421356)
            if ng < g[nk] - 1e-6:
                g[nk] = ng
                parent[nk] = k
                heapq.heappush(heap, (ng + h_to_goal(ni, nj), counter, nk))
                counter += 1

        # change layer through a via
        if grid.via_ok(i, j):
            for other in layers:
                if other == layer:
                    continue
                nk = idx(other, i, j)
                ng = g[k] + via_cost
                if ng < g[nk] - 1e-6:
                    g[nk] = ng
                    parent[nk] = k
                    heapq.heappush(heap, (ng + h_to_goal(i, j), counter, nk))
                    counter += 1

    if goal_k is None:
        legal = sum(1 for lay in layers
                    for i in range(grid.nx) for j in range(grid.ny)
                    if grid.track_ok(lay, i, j))
        print(f"    [search] expanded {expanded} cell(s); "
              f"{legal} legal track cell(s) on the whole board")
        d, at, _ = closest
        if at is None:
            print("    [search] never left its starting cells")
        else:
            layer, i, j = at
            x, y = grid.xy(i, j)
            print(f"    [search] closest approach to any goal: "
                  f"{d * grid.step:.2f}mm at ({x:.2f},{y:.2f}) on "
                  f"{'F.Cu' if layer == pcbnew.F_Cu else 'B.Cu'}")
            for lay in layers:
                gap, who = grid.cell(lay, i, j)
                print(f"      here {lay}: gap {gap:6.3f}mm "
                      f"(track needs {grid.keep:.2f}, via {grid.pad_keep:.2f})  "
                      f"track_ok={grid.track_ok(lay, i, j)}")
            print(f"      here via_ok={grid.via_ok(i, j)}")
            # The goal we got nearest to, and what is wrong with it.
            best = min(goals, key=lambda g: max(abs(g[1] - i), abs(g[2] - j)))
            gi, gj = best[1], best[2]
            gx, gy = grid.xy(gi, gj)
            print(f"      nearest goal cell ({gx:.2f},{gy:.2f}) on "
                  f"{'F.Cu' if best[0] == pcbnew.F_Cu else 'B.Cu'}: "
                  f"track_ok={grid.track_ok(best[0], gi, gj)} "
                  f"via_ok={grid.via_ok(gi, gj)}")
        return None

    path = []
    k = goal_k
    while k != -1:
        lay_i, rem = divmod(k, grid.n())
        i, j = divmod(rem, ny)
        path.append((layers[lay_i], i, j))
        k = parent[k]
    path.reverse()
    return path


# --------------------------------------------------------------------------
# emit
# --------------------------------------------------------------------------


def layer_runs(path):
    """Split the cell path into maximal runs that stay on one layer."""
    runs = [[path[0]]]
    for cell in path[1:]:
        if cell[0] != runs[-1][-1][0]:
            runs.append([cell])
        else:
            runs[-1].append(cell)
    return runs


def merge_run(run):
    """Collinear-merged (layer, i0, j0, i1, j1) segments for one layer run."""
    if len(run) < 2:
        return []
    segs = []
    start = run[0]
    prev = None
    for k in range(1, len(run)):
        d = (run[k][1] - run[k - 1][1], run[k][2] - run[k - 1][2])
        if prev is not None and d != prev:
            segs.append((run[0][0], start[1], start[2],
                         run[k - 1][1], run[k - 1][2]))
            start = run[k - 1]
        prev = d
    segs.append((run[0][0], start[1], start[2], run[-1][1], run[-1][2]))
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", nargs="*", default=None)
    ap.add_argument("--ref", default="J1")
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--clearance", type=float, default=0.2)
    #: Slack demanded on top of the board's own rules. The rule is a legal
    #: target, not a tight one -- J1's pads are on 0.5mm pitch, which leaves a
    #: 0.1mm-wide window for an escape track, and asking for even 0.05mm more
    #: than the rule closes it.
    #: Must exceed half a grid diagonal, or a run between two legal sample
    #: points can bow closer to its neighbour than either endpoint measured:
    #: a 0.1mm diagonal step strays up to 0.071mm, so 0.1 keeps the true
    #: clearance at or above the rule everywhere along the track.
    ap.add_argument("--safety", type=float, default=0.1)
    ap.add_argument("--via-cost", type=float, default=25.0)
    #: Lock the copper this emits. Freerouting treats a locked track as a
    #: `(type fix)` wire -- KiCad's Specctra export maps IsLocked() onto that
    #: -- which is the only way to pre-route a net the autorouter cannot do
    #: itself and have it survive: as an ordinary `(type route)` wire the
    #: router simply rips it up wherever it is in the way, and the net ends up
    #: back in pieces.
    ap.add_argument("--lock", action="store_true",
                    help="lock the emitted tracks and vias so the autorouter "
                         "routes around them instead of ripping them up")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--conflict", action="store_true",
                    help="let the path cross other nets' clearance, reporting "
                         "what it had to cross (sizing a rip-up)")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    ds = board.GetDesignSettings()
    edge_clear = ds.m_CopperEdgeClearance / S
    print(f"edge clearance rule: {edge_clear} mm")

    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    keep = a.clearance + TRACK_W / 2 + a.safety
    pad_keep = a.clearance + VIA_DIA / 2 + a.safety
    edge_keep = edge_clear + TRACK_W / 2 + a.safety
    via_edge_keep = edge_clear + VIA_DIA / 2 + a.safety

    todo = a.nets
    if todo is None:
        todo = sys.exit("--nets is required (auto-detect not wired up yet)")

    for name in todo:
        own = net_items(board, name)
        if not own:
            print(f"{name}: no copper found, skipping")
            continue
        pad = start_pad(board, a.ref, str(int(name[3:]) + 1))
        if pad is None:
            print(f"{name}: no {a.ref} pad found")
            continue

        others = [it for it in board.GetTracks() if it.GetNetname() != name]
        for fp in board.GetFootprints():
            others.extend(p for p in fp.Pads() if p.GetNetname() != name)

        grid = Grid(board, a.step, keep, edge_keep, pad_keep, via_edge_keep)
        grid.build(layers, others)

        # Start: cells overlapping the open pad.
        pp = pad.GetPosition()
        pc = (pp.x / S, pp.y / S)
        si, sj = grid.ij(*pc)
        start = []
        for di in range(-3, 4):
            for dj in range(-3, 4):
                i, j = si + di, sj + dj
                if 0 <= i < grid.nx and 0 <= j < grid.ny:
                    x, y = grid.xy(i, j)
                    r = pad.GetBoundingBox()
                    if (r.GetLeft() / S <= x <= r.GetRight() / S
                            and r.GetTop() / S <= y <= r.GetBottom() / S):
                        start.append((pcbnew.F_Cu, i, j))
        if not start:
            start = [(pcbnew.F_Cu, si, sj)]
        print(f"{name}: start {len(start)} cell(s) around {pc}, "
              f"pad layer F.Cu")

        # Goal: the centre of any other same-net item.
        goals = set()
        pad_uuid = pad.m_Uuid.AsString()
        for it in own:
            # Compare by uuid, not identity: pcbnew hands back a new proxy
            # object on every GetFootprints()/Pads() walk, so `it is pad` is
            # False even for the very pad we started from -- which then stayed
            # in the goal set and made the search "succeed" in one cell.
            if isinstance(it, pcbnew.PAD) and it.m_Uuid.AsString() == pad_uuid:
                continue
            shape = item_shape(it)
            if shape is None:
                continue
            cx, cy = (shape[0] + shape[2]) / 2, (shape[1] + shape[3]) / 2
            layers_here = [l for l in layers if on_layer(it, l)]
            for l in layers_here:
                i, j = grid.ij(cx, cy)
                if 0 <= i < grid.nx and 0 <= j < grid.ny:
                    goals.add((l, i, j))
        print(f"{name}: {len(goals)} goal cell(s) from {len(own)} own items")

        if not goals:
            print(f"{name}: nothing to connect to")
            continue

        path = astar_dual(grid, layers, start, goals, a.via_cost,
                          conflict=a.conflict)
        if path is None:
            print(f"{name}: NO PATH FOUND")
            continue

        nvia = sum(1 for k in range(1, len(path))
                   if path[k][0] != path[k - 1][0])
        length = 0.0
        for k in range(1, len(path)):
            if path[k][0] == path[k - 1][0]:
                dx = path[k][1] - path[k - 1][1]
                dy = path[k][2] - path[k - 1][2]
                length += (dx * dx + dy * dy) ** 0.5 * a.step
        print(f"{name}: path {len(path)} cells, {length:.1f}mm, {nvia} via(s)")

        if a.conflict:
            blockers = {}
            for layer, i, j in path:
                d, who = grid.cell(layer, i, j)
                if who >= 0 and d < keep:
                    blockers.setdefault(who, [0, d])
                    blockers[who][0] += 1
                    blockers[who][1] = min(blockers[who][1], d)
            print(f"{name}: crosses {len(blockers)} other-net item(s):")
            for who, (cells, worst) in sorted(blockers.items(),
                                              key=lambda kv: -kv[1][0]):
                it = others[who]
                kind = (it.GetClass() if hasattr(it, "GetClass") else "?")
                print(f"    {cells:4d} cell(s), worst gap {worst:+.3f}mm  "
                      f"net {it.GetNetname()}  {kind}")
            continue

        runs = layer_runs(path)
        tracks, vias = [], []
        for run in runs:
            tracks.extend(merge_run(run))
        # The search changes layer in single-cell steps, so an obstacle it
        # cannot pass often shows up as F->B->F->B within a few tenths of a
        # millimetre -- eight vias in a 0.3mm blob, each one a min-via-spacing
        # DRC error. One via covers that whole cluster: it is 0.6mm across, so
        # it spans every cell the oscillation touched, and the little
        # same-layer runs between them sit inside its copper.
        for k in range(1, len(runs)):
            c = runs[k][0]
            x, y = grid.xy(c[1], c[2])
            if any((x - vx) ** 2 + (y - vy) ** 2 < VIA_DIA ** 2
                   for vx, vy in vias):
                continue
            vias.append((x, y))

        netinfo = board.FindNet(name)
        for x, y in vias:
            if not a.dry_run:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(int(x * S), int(y * S)))
                v.SetWidth(int(VIA_DIA * S))
                v.SetDrill(int(0.3 * S))
                v.SetNet(netinfo)
                v.SetLocked(a.lock)
                board.Add(v)
        for layer, i0, j0, i1, j1 in tracks:
            if i0 == i1 and j0 == j1:
                continue
            x0, y0 = grid.xy(i0, j0)
            x1, y1 = grid.xy(i1, j1)
            if not a.dry_run:
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(int(x0 * S), int(y0 * S)))
                t.SetEnd(pcbnew.VECTOR2I(int(x1 * S), int(y1 * S)))
                t.SetWidth(int(TRACK_W * S))
                t.SetLayer(layer)
                t.SetNet(netinfo)
                t.SetLocked(a.lock)
                board.Add(t)

        for layer, i0, j0, i1, j1 in tracks[:4]:
            x0, y0 = grid.xy(i0, j0)
            x1, y1 = grid.xy(i1, j1)
            print(f"    {layer}: ({x0:.1f},{y0:.1f}) -> ({x1:.1f},{y1:.1f})")
        for x, y in vias[:4]:
            print(f"    via  ({x:.1f},{y:.1f})")
        print(f"    ... {len(tracks)} track(s), {len(vias)} via(s)")

    if not a.dry_run:
        board.BuildConnectivity()
        pcbnew.SaveBoard(a.board, board)
        print(f"\nsaved {a.board}")


if __name__ == "__main__":
    main()
