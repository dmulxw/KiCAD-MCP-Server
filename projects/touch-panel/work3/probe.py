"""Rip-up planner for the J1 fan-out.

Same clearance model as ``scripts/route-open-nets.py`` -- a cell is legal for a
0.2mm track when it is ``clearance + TRACK_W/2 + safety`` away from every other
net's copper and ``edge_clearance + TRACK_W/2 + safety`` from the board edge --
but the pieces that made the original unusable are replaced:

* the distance maps are numpy, so the per-item inner loop is vectorised;
* the A* heuristic is a precomputed octile distance transform instead of a
  scan over every goal cell on every expansion. A ROW net's goal set is its
  whole trunk plus every touch pad on the row: thousands of cells, which made
  each expansion O(thousands) and made ``--conflict`` (which by design explores
  the entire board) never terminate.

In ``--conflict`` mode the search is allowed to cross other nets' clearance at
a steep cost, and the report names every item it had to cross. That list *is*
the rip-up: those are the nets that must be lifted and re-routed for the net to
get out, and the crossing count ranks them by how badly they are in the way.

    python probe.py <board> --nets ROW3 ROW5 [--safety 0] [--conflict]
"""
import argparse
import heapq

import numpy as np
import pcbnew

S = 1e6
TRACK_W = 0.2
VIA_DIA = 0.6
INF = np.float32(1e9)
SQRT2 = 2 ** 0.5


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------


class Ghost:
    """A removed item, re-presented to the grid as an obstacle.

    A rip-up router lifts a corridor and then routes into the hole it left,
    which is the point -- the hole is what makes room. But it also means the
    search is blind to what it is cutting through. On this board that is not
    a detail: the row trunks run horizontally on F.Cu, the escape has to run
    vertically, and a search that cannot see the trunks takes the straight
    line down the middle of the panel on F.Cu -- slicing every one of them at
    whatever distance the grid happened to produce, 0.15mm in the event.

    A ghost puts a lifted item back on the map as an obstacle only, with no
    copper behind it and nothing written to the board. Crossing it then costs
    a via pair, and the search pays that instead of the knife.
    """

    __slots__ = ("shape", "lset")

    def __init__(self, shape, layers):
        self.shape = shape
        self.lset = set(layers)


def item_shape(item):
    """One piece of copper as (x0, y0, x1, y1, r, is_box), in mm.

    Pads and vias come back as boxes -- a pad *is* its bounding box, so running
    one through the segment distance would measure the gap to the box diagonal
    and leave most of a 5mm touch pad reading as free copper.

    Vias are measured by bounding box rather than ``GetWidth()``: in this build
    ``PCB_VIA`` inherits ``PCB_TRACK::GetWidth()``, which asserts unless passed a
    layer, and the assert floods stderr once per via per build.
    """
    if isinstance(item, Ghost):
        return item.shape
    if isinstance(item, pcbnew.PAD):
        bb = item.GetBoundingBox()
        return (bb.GetLeft() / S, bb.GetTop() / S,
                bb.GetRight() / S, bb.GetBottom() / S, 0.0, True)
    if isinstance(item, pcbnew.PCB_VIA):
        bb = item.GetBoundingBox()
        return (bb.GetLeft() / S, bb.GetTop() / S,
                bb.GetRight() / S, bb.GetBottom() / S, 0.0, True)
    if isinstance(item, pcbnew.PCB_TRACK):
        s, e = item.GetStart(), item.GetEnd()
        return (min(s.x, e.x) / S, min(s.y, e.y) / S,
                max(s.x, e.x) / S, max(s.y, e.y) / S,
                item.GetWidth() / S / 2, False)
    return None


def item_seg(item):
    """A track's real endpoints, or None for anything that really is a box.

    item_shape() hands back a track's *bounding box*, which is exactly what the
    windowing in NGrid.build wants and exactly what a distance query must not
    use.  For an axis-aligned track the bbox corners are the endpoints, so the
    two agree and the mistake is invisible; for a diagonal track they are the
    anti-diagonal, so the field measures a segment that is not on the board.
    The cost of that is not symmetric: the phantom segment shelters a corridor
    the real one occupies, a later route reads it as clear ground, and the
    emitter lays copper straight through another net's track.  Measured on
    _r1.kicad_pcb: ROW5's 45-degree feeder (95.450,163.850)->(100.950,158.350)
    sits at true distance -0.10mm from a ROW9 vertex that the grid scored at
    3.2234mm -- one of 11 shorts, 28 crossings and 13 clearance errors.
    """
    if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
        s, e = item.GetStart(), item.GetEnd()
        return (s.x / S, s.y / S, e.x / S, e.y / S)
    return None


def on_layer(item, layer):
    if isinstance(item, Ghost):
        return layer in item.lset
    if isinstance(item, pcbnew.PAD):
        return item.IsOnLayer(layer)
    if isinstance(item, pcbnew.PCB_VIA):
        return True
    if isinstance(item, pcbnew.PCB_TRACK):
        return item.IsOnLayer(layer)
    return False


# --------------------------------------------------------------------------
# grid
# --------------------------------------------------------------------------


class NGrid:
    """Distance-to-other-net-copper and legality, as numpy arrays."""

    def __init__(self, board, step, keep, edge_keep, pad_keep, via_edge_keep,
                 layers):
        self.step = step
        self.keep = keep
        self.edge_keep = edge_keep
        self.pad_keep = pad_keep
        self.via_edge_keep = via_edge_keep
        self.layers = layers
        bb = board.GetBoardEdgesBoundingBox()
        self.bb = (bb.GetLeft() / S, bb.GetTop() / S,
                   bb.GetRight() / S, bb.GetBottom() / S)
        pad = 0.5
        self.x0 = self.bb[0] - pad
        self.y0 = self.bb[1] - pad
        self.nx = int((self.bb[2] + pad - self.x0) / step) + 1
        self.ny = int((self.bb[3] + pad - self.y0) / step) + 1
        self.n = self.nx * self.ny
        self.stamp = max(keep, edge_keep, pad_keep) + 0.5
        self.D = {}
        self.OWN = {}

        xs = self.x0 + np.arange(self.nx) * step
        ys = self.y0 + np.arange(self.ny) * step
        self.X, self.Y = np.meshgrid(xs, ys)          # (ny, nx)
        self.EG = np.minimum.reduce([self.X - self.bb[0], self.bb[2] - self.X,
                                     self.Y - self.bb[1], self.bb[3] - self.Y])

    def ij(self, x, y):
        return (int(round((x - self.x0) / self.step)),
                int(round((y - self.y0) / self.step)))

    def xy(self, i, j):
        return self.x0 + i * self.step, self.y0 + j * self.step

    def build(self, items):
        for lay in self.layers:
            self.D[lay] = np.full((self.ny, self.nx), INF, np.float32)
            self.OWN[lay] = np.full((self.ny, self.nx), -1, np.int32)
        for no, it in enumerate(items):
            shape = item_shape(it)
            if shape is None:
                continue
            ax, ay, bx, by, r, box = shape
            reach = self.stamp if box else r + self.stamp
            i0 = max(0, int((ax - reach - self.x0) / self.step))
            i1 = min(self.nx - 1, int((bx + reach - self.x0) / self.step) + 1)
            j0 = max(0, int((ay - reach - self.y0) / self.step))
            j1 = min(self.ny - 1, int((by + reach - self.y0) / self.step) + 1)
            if i1 < i0 or j1 < j0:
                continue
            px = self.X[j0:j1 + 1, i0:i1 + 1]
            py = self.Y[j0:j1 + 1, i0:i1 + 1]
            if box:
                dx = np.maximum(np.maximum(ax - px, 0.0), px - bx)
                dy = np.maximum(np.maximum(ay - py, 0.0), py - by)
                d = np.sqrt(dx * dx + dy * dy).astype(np.float32)
            else:
                # The window above is built from the bbox (correct); the
                # distance must run against the real centreline, not the bbox
                # diagonal.  See item_seg().
                sx, sy, ex, ey = item_seg(it) or (ax, ay, bx, by)
                d = (self._seg_dist(px, py, sx, sy, ex, ey)
                     - np.float32(r)).astype(np.float32)
            for lay in self.layers:
                if not on_layer(it, lay):
                    continue
                sub = self.D[lay][j0:j1 + 1, i0:i1 + 1]
                m = d < sub
                if m.any():
                    sub[m] = d[m]
                    self.OWN[lay][j0:j1 + 1, i0:i1 + 1][m] = no

        self.OK = {lay: (self.D[lay] >= np.float32(self.keep))
                   & (self.EG >= self.edge_keep) for lay in self.layers}
        self.VOK = np.ones((self.ny, self.nx), bool)
        for lay in self.layers:
            self.VOK &= (self.D[lay] >= np.float32(self.pad_keep))
        self.VOK &= (self.EG >= self.via_edge_keep)

    @staticmethod
    def _seg_dist(px, py, ax, ay, bx, by):
        if ax == bx and ay == by:
            return np.sqrt((px - ax) ** 2 + (py - ay) ** 2).astype(np.float32)
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = ((px - ax) * dx + (py - ay) * dy) / L2
        t = np.clip(t, 0.0, 1.0)
        return np.sqrt((px - (ax + t * dx)) ** 2
                       + (py - (ay + t * dy)) ** 2).astype(np.float32)


def octile_dt(mask, step):
    """Exact octile distance (in steps) to the nearest True cell of `mask`.

    Chamfer 3x3, two passes. The within-row terms have a closed form --
    ``min_t<=i (a[t] + (i-t))`` is ``i + cummin(a - t)`` -- so each row is a
    couple of vectorised ops and the whole transform is O(ny) python steps
    rather than O(cells).
    """
    ny, nx = mask.shape
    d = np.where(mask, np.float32(0.0), INF).astype(np.float32)
    ar = np.arange(nx, dtype=np.float32)

    def row_fwd(a):
        return np.minimum.accumulate(a - ar) + ar

    def row_bwd(a):
        return np.minimum.accumulate((a + ar)[::-1])[::-1] - ar

    for j in range(ny):
        if j:
            p = d[j - 1]
            np.minimum(d[j], p + np.float32(1.0), out=d[j])
            np.minimum(d[j], np.concatenate(
                ([INF], p[:-1])) + np.float32(SQRT2), out=d[j])
            np.minimum(d[j], np.concatenate(
                (p[1:], [INF])) + np.float32(SQRT2), out=d[j])
        d[j] = row_fwd(d[j])
    for j in range(ny - 1, -1, -1):
        if j < ny - 1:
            p = d[j + 1]
            np.minimum(d[j], p + np.float32(1.0), out=d[j])
            np.minimum(d[j], np.concatenate(
                ([INF], p[:-1])) + np.float32(SQRT2), out=d[j])
            np.minimum(d[j], np.concatenate(
                (p[1:], [INF])) + np.float32(SQRT2), out=d[j])
        d[j] = row_bwd(d[j])
    return d


# --------------------------------------------------------------------------
# A*
# --------------------------------------------------------------------------


def astar(grid, start_cells, goals, via_cost, conflict, soft=None):
    """A* over (layer, j, i). Returns (path, crossing) or (None, crossing).

    `soft` is an optional {layer: array} of extra per-cell costs on top of the
    step cost. The grid stays hard -- illegal cells are still walls -- but a
    cell that merely *hugs* another net's copper can be made expensive, which
    is how a route is steered down an empty lane instead of along a crowded
    one. Keep it bounded: `conflict=True` already makes every cell traversable
    and the search then explodes, so this is the gentler tool.
    """
    ny, nx, n = grid.ny, grid.nx, grid.n
    layers = grid.layers
    li = {lay: k for k, lay in enumerate(layers)}
    goal_mask = np.zeros((ny, nx), bool)
    for lay, i, j in goals:
        goal_mask[j, i] = True
    gmask = {lay: np.zeros((ny, nx), bool) for lay in layers}
    for lay, i, j in goals:
        gmask[lay][j, i] = True
    H = {lay: octile_dt(gmask[lay], grid.step) for lay in layers}
    # A layer carrying no goal cell of its own is still usable -- you reach it
    # by via and cross back.  octile_dt cannot say so: an all-False mask gives
    # it nothing to pull the transform down from, so it returns INF (1e9) for
    # every cell of that layer.  That is not a lower bound but an infinite
    # overestimate, and an overestimating H is not just inadmissible, it
    # reorders the heap: every node on that layer gets f ~ 1e9 and pops last,
    # so the via transition is never reached before the goal is found on the
    # layer the search started on.  Vias then work ONLY when the goal itself
    # sits on the other layer.  Measured on the ROW3 pair: fragments 3.18mm
    # apart, the same cell one layer down VOK on both layers and 18 cells away,
    # yet the search returned a 146.41mm lap over the top of the board with
    # zero vias -- while a goal placed on B.Cu came back in 15 cells through a
    # via.  Identical geometry, opposite answer, decided only by which layer
    # held the goal.
    #
    # Lower bound for a goal-less layer: you must pay for at least one via and
    # then cover the octile distance to the goal from that same cell, so
    # ``via_cost + min over goal-bearing layers`` is admissible -- walking on
    # the goal-less layer first can only add cost.  With two layers and a
    # single-layer goal this is exact.
    live = [lay for lay in layers if gmask[lay].any()]
    if live and len(live) < len(layers):
        best = np.minimum.reduce([H[lay] for lay in live])
        for lay in layers:
            if not gmask[lay].any():
                H[lay] = best + np.float32(via_cost)

    total = n * len(layers)
    g = np.full(total, INF, np.float64)
    parent = np.full(total, -1, np.int64)

    def kidx(lay, i, j):
        return li[lay] * n + j * nx + i

    def unpack(k):
        l, rem = divmod(k, n)
        j, i = divmod(rem, nx)
        return layers[l], i, j

    heap = []
    ctr = 0
    for lay, i, j in start_cells:
        k = kidx(lay, i, j)
        g[k] = 0.0
        heapq.heappush(heap, (float(H[lay][j, i]), ctr, k))
        ctr += 1

    NB = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    OK = grid.OK
    D = grid.D
    keep = grid.keep
    crossing = {}
    goal_k = None
    expanded = 0
    closest = (1e18, None)

    while heap:
        f, _, k = heapq.heappop(heap)
        lay, i, j = unpack(k)
        if f > g[k] + H[lay][j, i] + 1e-6:
            continue
        expanded += 1
        if gmask[lay][j, i]:
            goal_k = k
            break
        h = H[lay][j, i]
        if h < closest[0]:
            closest = (h, (lay, i, j))

        for di, dj in NB:
            ni, nj = i + di, j + dj
            if ni < 0 or nj < 0 or ni >= nx or nj >= ny:
                continue
            if di and dj:
                # A diagonal step needs both orthogonal neighbours open too.
                # Testing only the destination lets the path cut the corner
                # between two obstacles whose keep-bands merely touch: the
                # destination cell is legal, the two cells it slips between
                # are not, and the track emitted on that diagonal runs
                # straight through the junction of two others. merge_run
                # emits a constant-direction run as one straight segment, so
                # the violation is real copper, not a sampling artefact --
                # measured on this board as 13 tracks_crossing, one short into
                # a via, and clearance grazes down to 0.0121mm against a
                # 0.2mm rule.
                if not (OK[lay][j, ni] and OK[lay][nj, i]):
                    if not conflict:
                        continue
                    if (D[lay][j, ni] < 0.0 or D[lay][nj, i] < 0.0
                            or D[lay][nj, ni] < 0.0):
                        continue
            extra = 0.0
            if not OK[lay][nj, ni]:
                if not conflict:
                    continue
                d = D[lay][nj, ni]
                if d < 0.0:
                    continue        # inside another net's copper: a short
                extra = (keep - float(d)) * 2000.0
                who = grid.OWN[lay][nj, ni]
                if who >= 0:
                    cur = crossing.get(who)
                    if cur is None:
                        crossing[who] = [0, float(d)]
                    crossing[who][0] += 1
                    if float(d) < crossing[who][1]:
                        crossing[who][1] = float(d)
            if di and dj:
                if not (OK[lay][j, i + di] and OK[lay][j + dj, i]):
                    if not conflict:
                        continue
                    for (ci, cj) in ((i + di, j), (i, j + dj)):
                        d = D[lay][cj, ci]
                        if d < 0.0:
                            extra = -1.0
                            break
                        extra += (keep - float(d)) * 2000.0
                    if extra < 0.0:
                        continue
            if soft is not None:
                extra += float(soft[lay][nj, ni])
            nk = kidx(lay, ni, nj)
            ng = g[k] + extra + (1.0 if (di == 0 or dj == 0) else SQRT2)
            if ng < g[nk] - 1e-6:
                g[nk] = ng
                parent[nk] = k
                heapq.heappush(heap, (ng + float(H[lay][nj, ni]), ctr, nk))
                ctr += 1

        if grid.VOK[j, i]:
            for other in layers:
                if other == lay:
                    continue
                nk = kidx(other, i, j)
                ng = g[k] + via_cost
                if ng < g[nk] - 1e-6:
                    g[nk] = ng
                    parent[nk] = k
                    heapq.heappush(heap, (ng + float(H[other][j, i]), ctr, nk))
                    ctr += 1

    if goal_k is None:
        return None, crossing, expanded, closest
    path = []
    k = goal_k
    while k != -1:
        path.append(unpack(k))
        k = parent[k]
    path.reverse()
    return path, crossing, expanded, closest
