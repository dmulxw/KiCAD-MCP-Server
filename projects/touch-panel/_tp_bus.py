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
        # NOT item.GetWidth(): on a PCB_VIA that overload asserts
        # (pcb_track.cpp:387) and returns a bogus radius.  Under a console the
        # assert raises a modal dialog and the whole run blocks forever.
        r = item.GetFrontWidth() / S / 2
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

    def __init__(self, board, step, keep, edge_keep, pad_keep, via_edge_keep,
                 align=None):
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
        if align is not None:
            # Snap the origin so the pad we start from sits exactly on a grid
            # point.  A 0.5mm-pitch FFC field leaves a track only 0.25mm of
            # clearance either side of the pad centre line, but a 0.2mm step
            # lands 0.05mm off that line and reads as blocked -- the escape
            # exists, the grid just could not express it.
            ax, ay = align
            self.x0 = ax - round((ax - self.x0) / step) * step
            self.y0 = ay - round((ay - self.y0) / step) * step
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



# --------------------------------------------------------------------------
# THE GROUP A BUS  (this file = route-open-nets.py's engine + this driver)
#
# The 595s' control and power bus is 25 of the 59 unconnected entries.  It has
# almost no copper, and it must run vertically past U1..U4 to reach pads 10-16
# of each register.  _tp_ripcorr.py proved the corridors for it exist but are
# occupied by the *other* broken group; _ripped.kicad_pcb is that board with
# Group B's corridor copper removed, and _tp_verify.py confirmed both corridors
# then hold one F vertical and one B vertical.
#
# Each net is routed as a CHAIN in the order listed: link k goes from endpoint
# k to the copper already laid for endpoints < k.  Goals are restricted to that
# copper, so the chain cannot jump ahead -- without that, a run from U2.11 can
# reach U3.11 just as cheaply as U1.11 and the chain skips a register.
#
# The register pads are listed in y order and the J1 pad LAST: the short
# register-to-register hops claim the corridor first and the single long run
# from the bottom edge lands in a board that already carries the bus, which is
# the easier search.  The five nets are routed in order of how constrained
# their escape is, not alphabetically.
#
#   python _tp_bus.py _ripped.kicad_pcb --dry-run
#   python _tp_bus.py _ripped.kicad_pcb --lock
# --------------------------------------------------------------------------

END = [
    ("IO10", [("U1", "11"), ("U2", "11"), ("U3", "11"), ("U4", "11"),
              ("J1", "2")]),
    ("IO11", [("U1", "12"), ("U2", "12"), ("U3", "12"), ("U4", "12"),
              ("J1", "3")]),
    ("IO12", [("U1", "13"), ("U2", "13"), ("U3", "13"), ("U4", "13"),
              ("J1", "4")]),
    ("IO9",  [("U1", "14"), ("J1", "1")]),
    ("+3V3", [("U1", "10"), ("U1", "16"), ("C1", "1"),
              ("U2", "10"), ("U2", "16"), ("C2", "1"),
              ("U3", "10"), ("U3", "16"), ("C3", "1"),
              ("U4", "10"), ("U4", "16"), ("C4", "1"),
              ("J1", "37")]),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", nargs="*", default=None)
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--clearance", type=float, default=0.2)
    ap.add_argument("--safety", type=float, default=0.1)
    ap.add_argument("--via-cost", type=float, default=25.0)
    ap.add_argument("--lock", action="store_true",
                    help="lock emitted copper so an autorouter routes around "
                         "it (Specctra (type fix)) instead of ripping it up")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--conflict", action="store_true")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    ds = board.GetDesignSettings()
    edge_clear = ds.m_CopperEdgeClearance / S
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    keep = a.clearance + TRACK_W / 2 + a.safety
    pad_keep = a.clearance + VIA_DIA / 2 + a.safety
    edge_keep = edge_clear + TRACK_W / 2 + a.safety
    via_edge_keep = edge_clear + VIA_DIA / 2 + a.safety
    print("edge clearance rule: %.3f mm   keep %.2f  pad_keep %.2f"
          % (edge_clear, keep, pad_keep))

    only = set(a.nets) if a.nets else None
    ntr = nvi = nfail = 0

    for (name, ends) in END:
        if only and name not in only:
            continue
        print("=" * 72)
        pads = []
        for (ref, num) in ends:
            p = start_pad(board, ref, num)
            if p is None:
                print("%s: %s pad %s NOT FOUND" % (name, ref, num))
            pads.append(p)
        print("%s: %d endpoint(s), routing as a chain"
              % (name, len([p for p in pads if p is not None])))

        # Each link goes from the next endpoint to the copper already laid.
        # Goals are restricted to what has been routed so far, so the chain
        # cannot jump ahead and connect U3 before U2.
        for idx in range(1, len(pads)):
            start = pads[idx]
            if start is None:
                continue
            pending = {p.m_Uuid.AsString() for p in pads[idx + 1:] if p is not None}
            own = [it for it in net_items(board, name)
                   if not (isinstance(it, pcbnew.PAD)
                           and it.m_Uuid.AsString() in pending)]
            others = [it for it in board.GetTracks() if it.GetNetname() != name]
            for fp in board.GetFootprints():
                others.extend(p for p in fp.Pads() if p.GetNetname() != name)

            pp0 = start.GetPosition()
            grid = Grid(board, a.step, keep, edge_keep, pad_keep,
                        via_edge_keep, align=(pp0.x / S, pp0.y / S))
            grid.build(layers, others)

            pp = start.GetPosition()
            pc = (pp.x / S, pp.y / S)
            si, sj = grid.ij(*pc)
            r = start.GetBoundingBox()
            start_cells = []
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    i, j = si + di, sj + dj
                    if 0 <= i < grid.nx and 0 <= j < grid.ny:
                        x, y = grid.xy(i, j)
                        if (r.GetLeft() / S <= x <= r.GetRight() / S
                                and r.GetTop() / S <= y <= r.GetBottom() / S):
                            start_cells.append((pcbnew.F_Cu, i, j))
            if not start_cells:
                start_cells = [(pcbnew.F_Cu, si, sj)]

            goals = set()
            pad_uuid = start.m_Uuid.AsString()
            for it in own:
                if isinstance(it, pcbnew.PAD) and it.m_Uuid.AsString() == pad_uuid:
                    continue
                shape = item_shape(it)
                if shape is None:
                    continue
                cx, cy = (shape[0] + shape[2]) / 2, (shape[1] + shape[3]) / 2
                for l in [l for l in layers if on_layer(it, l)]:
                    i, j = grid.ij(cx, cy)
                    if 0 <= i < grid.nx and 0 <= j < grid.ny:
                        goals.add((l, i, j))

            tag = "%s[%d] %s->%s" % (name, idx, ends[idx][0] + "." + ends[idx][1],
                                     ends[0][0] + "." + ends[0][1])
            if not goals:
                print("  %-22s no goals (nothing to connect to)" % tag)
                nfail += 1
                continue

            path = astar_dual(grid, layers, start_cells, goals, a.via_cost,
                              conflict=a.conflict)
            if path is None:
                print("  %-22s NO PATH   (%d goal cell(s))" % (tag, len(goals)))
                nfail += 1
                continue

            runs = layer_runs(path)
            tracks = []
            for run in runs:
                tracks.extend(merge_run(run))
            vias = []
            for k in range(1, len(runs)):
                c = runs[k][0]
                x, y = grid.xy(c[1], c[2])
                if any((x - vx) ** 2 + (y - vy) ** 2 < VIA_DIA ** 2
                       for vx, vy in vias):
                    continue
                vias.append((x, y))

            length = 0.0
            for k in range(1, len(path)):
                if path[k][0] == path[k - 1][0]:
                    dx = path[k][1] - path[k - 1][1]
                    dy = path[k][2] - path[k - 1][2]
                    length += (dx * dx + dy * dy) ** 0.5 * a.step

            if a.conflict:
                blockers = {}
                for layer, i, j in path:
                    d, who = grid.cell(layer, i, j)
                    if who >= 0 and d < keep:
                        blockers.setdefault(who, [0, d])
                        blockers[who][0] += 1
                        blockers[who][1] = min(blockers[who][1], d)
                print("  %-22s %5.1fmm %2d via(s)  crosses %d other-net item(s)"
                      % (tag, length, len(vias), len(blockers)))
                for who, (cells, worst) in sorted(blockers.items(),
                                                  key=lambda kv: -kv[1][0])[:5]:
                    it = others[who]
                    print("        %4d cell(s) worst %+.3fmm  net %s"
                          % (cells, worst, it.GetNetname()))
                continue

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
            ntr += len(tracks)
            nvi += len(vias)
            print("  %-22s %6.1fmm  %2d track(s)  %2d via(s)"
                  % (tag, length, len(tracks), len(vias)))

    print("=" * 72)
    print("TOTAL: %d track(s), %d via(s), %d link(s) with no path"
          % (ntr, nvi, nfail))
    if not a.dry_run:
        board.BuildConnectivity()
        pcbnew.SaveBoard(a.board, board)
        print("saved %s" % a.board)


if __name__ == "__main__":
    main()
