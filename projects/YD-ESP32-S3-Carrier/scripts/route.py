"""Maze-route the YD-ESP32-S3 carrier.

A* over a 0.2 mm grid spanning F.Cu and B.Cu.  The through-hole headers reach
both layers on their own, so for those a via is only needed to switch layers
mid-trace and the cost function discourages it.  The power section is SMD, and an
SMD pad exists on exactly one layer: it blocks only that layer, and a trace can
only land on it there.  Both facts are tracked per pad.

Grid and clearance are not free parameters -- see the notes on GRID and CLEAR
below.  A 2.54 mm header pitch against a grid that divides it exactly makes every
inter-pad gap share one phase, and a whole header row can end up impassable.

GND is deliberately not routed: it is left to the copper pour (see pour.py).

The script is re-runnable -- it deletes every track and via on the board first.

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" scripts/route.py
"""
import heapq
import math
import sys

import numpy as np
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

BOARD_W, BOARD_H = 100.0, 64.0

# 0.2 mm, deliberately *not* 0.254.  The headers are 2.54 mm pitch, and 2.54 is 10
# steps of 0.254 exactly -- so every gap between two pins in a row shares one grid
# phase, and a row is either passable at every pin or at none of them.  For J1 and
# J2 the phase lands badly and the whole 22-pin row becomes a wall across the board.
# At 0.2 mm the pitch is 12.7 steps, the phase drifts along the row, and the gaps
# come out individually.
GRID = 0.20           # mm per grid step

# 0.16 rather than 0.20 for the same reason, one step further: the gap between two
# header pads' halos is 2.54 - 2*(0.85 + CLEAR + 0.15).  At CLEAR 0.20 that is 0.14 mm
# -- narrower than a grid cell, so a gap only takes a trace if the phase happens to
# line up.  At 0.16 it is 0.22 mm: wider than the grid, so a legal path between
# adjacent header pins exists by construction.  0.16 mm is also 6.3 mil, inside the
# 6 mil / 0.15 mm clearance every fab offers at standard price.
CLEAR = 0.16          # copper-to-copper clearance, mm
EDGE_KEEPOUT = 1.00   # track centreline must stay this far from the board edge
VIA_D, VIA_DRILL = 0.60, 0.30
VIA_COST = 6.0        # mm-equivalent charged for a layer change
HOLE_CLEAR = 0.50     # extra copper-free ring around a non-plated hole

DEFAULT_W = 0.30
# The two nets that touch the MT3608 are 0.60 rather than 1.00 on purpose.  SOT-23-6
# pads are on 0.95 mm pitch and only 0.60 mm tall, so a 1.00 mm trace centred on one
# needs 0.70 mm of clearance to the neighbour's copper edge, which is 0.65 mm away --
# geometrically impossible, not merely tight.  0.60 mm copper still carries ~1.5 A on
# 1 oz and these runs are a few mm long.
WIDTHS = {"+5V": 1.00, "VBAT": 1.00, "VBAT_SW": 0.60, "SW_NODE": 0.60, "+3V3": 0.80}

# No vias in the audio module's flat-lay area -- the module body sits there -- and
# none in the strip the dev board's USB shell overhangs at the bottom edge.
VIA_BAN = [(43.0, 11.0, 74.0, 32.0), (18.0, 60.0, 29.0, 64.0)]

# grid layer index -> pcbnew layer id.  B_Cu is 2, not 1 (1 is F.Mask).
LAYER_ID = (pcbnew.F_Cu, pcbnew.B_Cu)

NX = int(BOARD_W / GRID) + 1
NY = int(BOARD_H / GRID) + 1
NL = 2


def gi(x):
    return min(NX - 1, max(0, int(round(x / GRID))))


def gj(y):
    return min(NY - 1, max(0, int(round(y / GRID))))


def mx(i):
    return i * GRID


def my(j):
    return j * GRID


def sign(v):
    return (v > 0) - (v < 0)


# --------------------------------------------------------------------- raster


def raster_circle(blocked, layer, cx, cy, r):
    i0, i1 = gi(cx - r) - 1, gi(cx + r) + 2
    j0, j1 = gj(cy - r) - 1, gj(cy + r) + 2
    i0, j0 = max(0, i0), max(0, j0)
    i1, j1 = min(NX, i1), min(NY, j1)
    if i0 >= i1 or j0 >= j1:
        return
    xs = (np.arange(i0, i1) * GRID)[:, None] - cx
    ys = (np.arange(j0, j1) * GRID)[None, :] - cy
    blocked[layer, i0:i1, j0:j1] |= (np.hypot(xs, ys) <= r)


def raster_rect(blocked, layer, x0, y0, x1, y1, r):
    i0 = max(0, gi(x0 - r) - 1)
    i1 = min(NX, gi(x1 + r) + 2)
    j0 = max(0, gj(y0 - r) - 1)
    j1 = min(NY, gj(y1 + r) + 2)
    if i0 >= i1 or j0 >= j1:
        return
    xs = (np.arange(i0, i1) * GRID)[:, None]
    ys = (np.arange(j0, j1) * GRID)[None, :]
    dx = np.maximum(np.maximum(x0 - xs, xs - x1), 0.0)
    dy = np.maximum(np.maximum(y0 - ys, ys - y1), 0.0)
    blocked[layer, i0:i1, j0:j1] |= (np.hypot(dx, dy) <= r)


def raster_seg(blocked, layer, x1, y1, x2, y2, r):
    """Everything within r mm of the segment -- the halo a track occupies."""
    i0 = max(0, gi(min(x1, x2) - r) - 1)
    i1 = min(NX, gi(max(x1, x2) + r) + 2)
    j0 = max(0, gj(min(y1, y2) - r) - 1)
    j1 = min(NY, gj(max(y1, y2) + r) + 2)
    if i0 >= i1 or j0 >= j1:
        return
    xs = (np.arange(i0, i1) * GRID)[:, None]
    ys = (np.arange(j0, j1) * GRID)[None, :]
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        d = np.hypot(xs - x1, ys - y1)
    else:
        t = np.clip(((xs - x1) * dx + (ys - y1) * dy) / L2, 0.0, 1.0)
        d = np.hypot(xs - (x1 + t * dx), ys - (y1 + t * dy))
    blocked[layer, i0:i1, j0:j1] |= (d <= r)


# ------------------------------------------------------------------- obstacles


def pad_layers(p):
    """Which of our two grid layers this pad actually has copper on.

    A through-hole pad is on both, an SMD pad on exactly one.  Getting this wrong
    is not merely wasteful: it lets the router run a track on the layer the pad
    is *not* on, "reach" it, and leave a net that reads as routed but is open.
    """
    ls = p.GetLayerSet()
    return tuple(l for l in (0, 1) if ls.Contains(LAYER_ID[l]))


def collect_shapes(board):
    """Static copper/hole obstacles: (net, kind, geometry, layers)."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            cx, cy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
            size = p.GetSize()
            hx, hy = pcbnew.ToMM(size.x) / 2.0, pcbnew.ToMM(size.y) / 2.0
            net = p.GetNetname()

            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                # bare hole: no copper, but the barrel blocks both layers
                out.append((net, "circle", (cx, cy, max(hx, hy) + HOLE_CLEAR), (0, 1)))
                continue

            layers = pad_layers(p) or (0, 1)
            shape = p.GetShape()
            if shape == pcbnew.PAD_SHAPE_CIRCLE and abs(hx - hy) < 1e-6:
                out.append((net, "circle", (cx, cy, hx), layers))
            else:
                bb = p.GetBoundingBox()
                out.append((net, "rect", (pcbnew.ToMM(bb.GetLeft()),
                                          pcbnew.ToMM(bb.GetTop()),
                                          pcbnew.ToMM(bb.GetRight()),
                                          pcbnew.ToMM(bb.GetBottom())), layers))
    return out


def pad_nodes(p):
    """Every grid node that sits on this pad's copper -- the nodes a trace may land on.

    Landing only on the pad *centre* is too strict for small-pitch parts.  A
    1.00 mm trace asked to hit a SOT-23 pad dead centre needs 0.70 mm of clearance
    from the neighbouring pad's edge, and there is only 0.65 mm of room -- but the
    same trace clears it comfortably if it lands 0.15 mm off centre, still well
    inside the copper.  Insetting by half a grid step keeps every returned node on
    the pad after rounding, so the trace always overlaps the copper it claims.
    """
    pos = p.GetPosition()
    cx, cy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
    size = p.GetSize()
    hx, hy = pcbnew.ToMM(size.x) / 2.0, pcbnew.ToMM(size.y) / 2.0

    if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
        r = max(hx, hy) - GRID / 2.0
        if r <= 0.0:
            return [(gi(cx), gj(cy))]
        i0, i1 = max(0, gi(cx - r) - 1), min(NX, gi(cx + r) + 2)
        j0, j1 = max(0, gj(cy - r) - 1), min(NY, gj(cy + r) + 2)
        return [(i, j) for i in range(i0, i1) for j in range(j0, j1)
                if math.hypot(mx(i) - cx, my(j) - cy) <= r]

    # GetBoundingBox is axis-aligned and every footprint here is on a multiple of
    # 90 degrees, so for a rect it is the pad's copper exactly.
    bb = p.GetBoundingBox()
    x0, y0 = pcbnew.ToMM(bb.GetLeft()) + GRID / 2.0, pcbnew.ToMM(bb.GetTop()) + GRID / 2.0
    x1, y1 = pcbnew.ToMM(bb.GetRight()) - GRID / 2.0, pcbnew.ToMM(bb.GetBottom()) - GRID / 2.0
    if x0 > x1 or y0 > y1:
        return [(gi(cx), gj(cy))]
    i0, i1 = max(0, gi(x0) - 1), min(NX, gi(x1) + 2)
    j0, j1 = max(0, gj(y0) - 1), min(NY, gj(y1) + 2)
    return [(i, j) for i in range(i0, i1) for j in range(j0, j1)
            if x0 <= mx(i) <= x1 and y0 <= my(j) <= y1]


def edge_mask():
    m = np.zeros((NL, NX, NY), dtype=bool)
    xs = np.arange(NX) * GRID
    ys = np.arange(NY) * GRID
    bad_x = (xs < EDGE_KEEPOUT) | (xs > BOARD_W - EDGE_KEEPOUT)
    bad_y = (ys < EDGE_KEEPOUT) | (ys > BOARD_H - EDGE_KEEPOUT)
    m[:] = bad_y[None, None, :]
    m[:, bad_x, :] = True
    return m


# ---------------------------------------------------------------------- router


class Router:
    def __init__(self, board):
        self.board = board
        self.shapes = collect_shapes(board)
        self.edge = edge_mask()
        self.tracks = []   # (net, layer, x1, y1, x2, y2, width)
        self.vias = []     # (net, x, y)
        self.fail_at = None   # pad the last route_net() could not reach, if any
        self.nets = {}
        for name, ni in board.GetNetsByName().items():
            self.nets[str(name)] = ni.GetNetCode()

        # net -> [(cx, cy, [(i, j), ...] landing nodes, (layer, ...))]
        self.pads = {}
        for fp in board.GetFootprints():
            for p in fp.Pads():
                net = p.GetNetname()
                if not net:
                    continue
                pos = p.GetPosition()
                self.pads.setdefault(net, []).append(
                    (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                     pad_nodes(p), pad_layers(p)))
        for net in self.pads:
            uniq = {}
            for entry in self.pads[net]:
                uniq[entry[:2]] = entry
            self.pads[net] = sorted(uniq.values())

    # -- blocking ----------------------------------------------------------
    @staticmethod
    def reserve(hw):
        """Halo radius for a via of the standard size -- used only where one may go."""
        return max(hw, VIA_D / 2.0)

    def blocked_for(self, net, hw):
        """(trace mask, via mask) for `net`.

        Two masks, not one.  A trace of half-width `hw` has to clear copper by
        `CLEAR + hw`; a via of radius VIA_D/2 by `CLEAR + VIA_D/2`.  Reserving the
        larger of the two everywhere -- which is what a single mask forces --
        inflates every obstacle by 0.20 mm on a 1.00 mm net and shuts the router
        out of gaps that are in fact legal for a trace.  The masks differ only for
        wide nets (where the trace needs more room) and narrow ones (where the via
        does); a via is checked against both, so neither can under-promise.
        """
        m = self.edge.copy()
        v = m.copy()
        tr_r = CLEAR + hw
        v_r = CLEAR + VIA_D / 2.0

        for other, kind, a, layers in self.shapes:
            if other == net:
                continue
            for layer in layers:
                if kind == "circle":
                    raster_circle(m, layer, a[0], a[1], a[2] + tr_r)
                    raster_circle(v, layer, a[0], a[1], a[2] + v_r)
                else:
                    x0, y0, x1, y1 = a
                    raster_rect(m, layer, x0, y0, x1, y1, tr_r)
                    raster_rect(v, layer, x0, y0, x1, y1, v_r)

        for onet, layer, x1, y1, x2, y2, w in self.tracks:
            if onet == net:
                continue
            raster_seg(m, layer, x1, y1, x2, y2, w / 2.0 + tr_r)
            raster_seg(v, layer, x1, y1, x2, y2, w / 2.0 + v_r)
        for vnet, vx, vy in self.vias:
            if vnet == net:
                continue
            for layer in (0, 1):
                raster_circle(m, layer, vx, vy, VIA_D / 2.0 + tr_r)
                raster_circle(v, layer, vx, vy, VIA_D / 2.0 + v_r)
        return m, v

    def via_ok(self, x, y):
        for x0, y0, x1, y1 in VIA_BAN:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return False
        return True

    # -- A* ----------------------------------------------------------------
    def astar(self, blocked, via_blocked, starts, goals, vias_banned=False):
        """starts: [(i,j,layer)];  goals: bool array (NL,NX,NY).

        Returns a list of (i,j,layer) from a start to some goal node, or None.
        `blocked` gates movement along a layer; `via_blocked` gates a layer change,
        which has to clear both layers by the via's own radius.
        """
        total = NL * NX * NY
        blk = bytearray(blocked.reshape(-1).tobytes())
        vblk = bytearray(via_blocked.reshape(-1).tobytes())
        board_area = NX * NY

        gidx = np.argwhere(goals)
        if len(gidx) == 0:
            return None
        gx = gidx[:, 1].astype(np.float64) * GRID
        gy = gidx[:, 2].astype(np.float64) * GRID
        cx, cy = float(gx.mean()), float(gy.mean())
        # "landmark + radius" bound: admissible because no goal is further from
        # the centroid than R, so this never overestimates the real cost.
        R = float(np.max(np.hypot(gx - cx, gy - cy)))

        def h(i, j):
            d = math.hypot(i * GRID - cx, j * GRID - cy) - R
            return d * 0.70710678 if d > 0.0 else 0.0

        heap = []
        for (i, j, l) in starts:
            k = l * board_area + i * NY + j
            if blk[k]:
                continue
            heapq.heappush(heap, (h(i, j), 0.0, k))

        goal_flat = set(np.flatnonzero(goals.reshape(-1)).tolist())
        D = GRID
        DD = GRID * 1.41421356
        DIRS = ((1, 0, D), (-1, 0, D), (0, 1, D), (0, -1, D),
                (1, 1, DD), (1, -1, DD), (-1, 1, DD), (-1, -1, DD))

        gs = [float("inf")] * total
        par = [-1] * total
        for (i, j, l) in starts:
            gs[l * board_area + i * NY + j] = 0.0
        heappush, heappop = heapq.heappush, heapq.heappop

        while heap:
            _, gc, k = heappop(heap)
            if k in goal_flat:
                path = []
                while k != -1:
                    l, rem = divmod(k, board_area)
                    path.append((rem // NY, rem % NY, l))
                    k = par[k]
                path.reverse()
                return path
            if gc > gs[k]:
                continue
            l, rem = divmod(k, board_area)
            i, j = rem // NY, rem % NY
            base = l * board_area

            for di, dj, step in DIRS:
                ni, nj = i + di, j + dj
                if ni < 0 or nj < 0 or ni >= NX or nj >= NY:
                    continue
                nk = base + ni * NY + nj
                if blk[nk]:
                    continue
                if di and dj and (blk[base + (i + di) * NY + j]
                                  or blk[base + i * NY + (j + dj)]):
                    continue                      # no corner cutting
                ng = gc + step
                if ng < gs[nk]:
                    gs[nk] = ng
                    par[nk] = k
                    heappush(heap, (ng + h(ni, nj), ng, nk))

            if not vias_banned:
                nb = (1 - l) * board_area + rem
                # a via is a barrel through both layers: it has to clear the
                # obstacles on the one it leaves *and* the one it arrives on
                if (not blk[nb] and not vblk[k] and not vblk[nb]
                        and self.via_ok(mx(i), my(j))):
                    ng = gc + VIA_COST
                    if ng < gs[nb]:
                        gs[nb] = ng
                        par[nb] = k
                        heappush(heap, (ng + h(i, j), ng, nb))
        return None

    # -- net routing -------------------------------------------------------
    def route_net(self, net):
        self.fail_at = None
        pads = self.pads.get(net, [])
        if len(pads) < 2:
            return True
        w = WIDTHS.get(net, DEFAULT_W)
        hw = w / 2.0
        blocked, via_blocked = self.blocked_for(net, hw)

        conn = np.zeros((NL, NX, NY), dtype=bool)

        def land(entry, mask):
            """Mark every layer this pad has copper on, at every node on the pad."""
            _, _, nodes, layers = entry
            for l in (layers or (0, 1)):
                for (i, j) in nodes:
                    mask[l, i, j] = True

        land(pads[0], conn)
        taken = [False] * len(pads)
        taken[0] = True
        done = 1
        while done < len(pads):
            # Prim-style: hook up the pad nearest the already-connected set
            best, bestd = None, 1e18
            for a, (ax, ay, _, _) in enumerate(pads):
                if taken[a]:
                    continue
                for b, (bx, by, _, _) in enumerate(pads):
                    if not taken[b]:
                        continue
                    d = (ax - bx) ** 2 + (ay - by) ** 2
                    if d < bestd:
                        bestd, best = d, a
            a = best
            _, _, nodes, layers = pads[a]
            starts = [(i, j, l) for l in (layers or (0, 1)) for (i, j) in nodes]
            path = self.astar(blocked, via_blocked, starts, conn)
            if path is None:
                # Remember *where* it stalled: the rip-up pass needs a local window,
                # and the net's own bounding box is useless here -- a net reaching
                # across the board overlaps nearly every other net that way.
                self.fail_at = pads[a][:2]
                print(f"  !! {net}: cannot reach pad {pads[a][:2]}")
                return False
            self.emit(net, path, w, blocked, via_blocked, hw)
            taken[a] = True
            done += 1

            # widen the tree so the next pad can hook onto this trace too.  The
            # trace carries through its own layer; the pad copper it terminates on
            # carries through every layer that pad has.
            for (pi, pj, pl) in path:
                conn[pl, pi, pj] = True
            land(pads[a], conn)
        return True

    def emit(self, net, path, w, blocked, via_blocked, hw):
        def direction(a, b):
            return (sign(b[0] - a[0]), sign(b[1] - a[1]), sign(b[2] - a[2]))

        pts = [path[0]]
        for k in range(1, len(path)):
            cur = path[k]
            if k + 1 < len(path) and direction(pts[-1], cur) == direction(cur, path[k + 1]):
                continue          # straight through -- keep collapsing
            pts.append(cur)

        tr_r = hw + CLEAR + hw                    # our copper + what a peer needs
        v_r = VIA_D / 2.0 + CLEAR + VIA_D / 2.0

        via_nodes = []
        for k in range(1, len(pts)):
            a, b = pts[k - 1], pts[k]
            if a[2] != b[2]:
                via_nodes.append(b)
                continue
            x1, y1, x2, y2 = mx(a[0]), my(a[1]), mx(b[0]), my(b[1])
            self.tracks.append((net, a[2], x1, y1, x2, y2, w))
            raster_seg(blocked, a[2], x1, y1, x2, y2, tr_r)
            raster_seg(via_blocked, a[2], x1, y1, x2, y2, v_r)

        for (i, j, l) in via_nodes:
            self.vias.append((net, mx(i), my(j)))
            for layer in (0, 1):
                raster_circle(blocked, layer, mx(i), my(j), tr_r)
                raster_circle(via_blocked, layer, mx(i), my(j), v_r)

        # Re-open this trace's own nodes.  Same-net copper is not an obstacle to
        # itself, and the connected set that A* aims at on the next pad *is* these
        # nodes -- leaving them behind their own halo would make every pad after
        # the second one unreachable.
        for (i, j, l) in path:
            blocked[l, i, j] = False
            via_blocked[l, i, j] = False
        return pts


# ------------------------------------------------------------- rip-up + retry


def rip(router, nets):
    """Lift the named nets' copper out of the router and hand it back.

    Nothing else has to be told about it: blocked_for() re-rasterises from
    router.tracks and router.vias on every call, so dropping the entries is all it
    takes for that copper to stop being an obstacle.
    """
    gone, keep = [], []
    for t in router.tracks:
        (gone if t[0] in nets else keep).append(t)
    router.tracks = keep
    keep = []
    for v in router.vias:
        (gone if v[0] in nets else keep).append(v)
    router.vias = keep
    return gone


def unrip(router, saved):
    """Put ripped copper back exactly as it was -- same list, same order."""
    for item in saved:
        (router.tracks if len(item) == 7 else router.vias).append(item)


def blocking_nets(router, net, at, radius, limit=10):
    """Nets with copper within `radius` of `at` -- the ones worth ripping up.

    Squared off against the *failing pad*, not the net's bounding box: a net that
    reaches across the board overlaps nearly everything by bbox, which is exactly the
    case where the decision matters and the bbox gives no information.  The window is
    what A* could not get through, so whatever is in it is what to move.

    Capped, smallest nets first: re-routing a two-segment run is cheap and usually
    succeeds, while tearing up +5V tends to move the failure rather than fix it.
    Past `limit` the net is left alone rather than gamble the whole board on it.
    """
    x0, x1 = at[0] - radius, at[0] + radius
    y0, y1 = at[1] - radius, at[1] + radius

    hit = {}
    for (onet, _l, ax, ay, bx, by, _w) in router.tracks:
        if onet != net and min(ax, bx) <= x1 and max(ax, bx) >= x0 \
                and min(ay, by) <= y1 and max(ay, by) >= y0:
            hit[onet] = hit.get(onet, 0) + 1
    for (vnet, vx, vy) in router.vias:
        if vnet != net and x0 <= vx <= x1 and y0 <= vy <= y1:
            hit[vnet] = hit.get(vnet, 0) + 1

    if len(hit) > limit:
        return None
    return sorted(hit, key=lambda n: hit[n])


def route_all(router, todo, radii=(5.0, 10.0, 18.0, 28.0), rounds=4):
    """Route every net, then repair the stragglers by ripping up what blocks them.

    This board has no order that routes cleanly -- the failures are pure congestion,
    and every one of them is a net that routes fine on an empty board.  So: route
    what routes, then for each failure lift the (few, small) nets around the pad it
    could not reach, lay the failure down first, and drop the others back on top.

    The radius escalates because the obstruction is not always next to the failing
    pad: a small window catches the net that pinched the corridor shut, a large one
    is needed when the whole approach is walled off.  Each round must make real
    progress or the next radius is tried.  Returns the nets still unrouted.

    Each net's stall point is remembered in `where`, not read back off the router:
    router.fail_at is overwritten by every route_net() call, so by the time this
    loop looks it belongs to whichever net was routed last -- usually not the one
    being repaired, which sends blocking_nets() to the wrong part of the board.
    """
    failed, where = [], {}
    for n in todo:
        if not router.route_net(n):
            failed.append(n)
            where[n] = router.fail_at

    for radius in radii:
        if not failed:
            break
        still, progress = [], False
        for net in failed:
            at = where.get(net)
            victims = blocking_nets(router, net, at, radius) if at else None
            if not victims:              # nothing in the way, or far too much
                still.append(net)
                continue
            saved = rip(router, set(victims))
            if router.route_net(net):
                progress = True
                where.pop(net, None)
                for v in victims:
                    if not router.route_net(v):
                        still.append(v)
                        where[v] = router.fail_at
            else:
                unrip(router, saved)     # restore byte for byte, give up on this one
                where[net] = router.fail_at
                still.append(net)
        if progress:
            # de-duplicated: one victim can be blocking several stragglers
            failed = list(dict.fromkeys(still))

    # Last resort, for a net whose wall is nowhere near the pad that stalled.  A long
    # net can be pinched anywhere along its length -- +5V has to leave a through-hole
    # header pin at 1.00 mm, which cannot pass between two pins at all, so it must go
    # the long way round the top of the board, and the rip-up window above will never
    # find that.  Clear the board, lay the straggler down first, then rebuild
    # everything else on top of it.  Expensive, but every straggler is known to route
    # on an empty board, and the rebuild may well strand a different net, so it runs
    # for a bounded number of rounds and keeps the best board it reached.
    for _ in range(rounds):
        if not failed:
            break
        star, others = failed[0], [n for n in todo if n != failed[0]]
        saved = rip(router, set(todo))            # board bare
        if not router.route_net(star):
            rip(router, {star})                   # drop the partial attempt
            unrip(router, saved)                  # and put the real board back
            failed = failed[1:] + [star]          # let the next one have a turn
            continue
        failed = [n for n in others if not router.route_net(n)]

    # A net that never finished leaves partial copper behind, which reads on the
    # board as a half-connected net.  Strip it: the rest of the routing was laid
    # down *around* that copper, so removing it can only free space, never collide.
    rip(router, set(failed))
    return failed


# ------------------------------------------------------------------- to board


def clear_routing(board):
    """Strip every track and via we routed, so the script is re-runnable.

    The removed proxies are returned rather than dropped: if Python destroys
    them while the board is still live, SWIG's bookkeeping gets corrupted and
    the next GetFootprints() hands back raw SwigPyObjects.

    Footprint-owned items are left alone.  GetTracks() lists them too, and U1's
    SOIC-8-1EP carries thermal vias in its exposed pad -- deleting those would
    quietly rewrite the footprint without them.
    """
    doomed = []
    for t in board.GetTracks():
        parent = t.GetParent()
        if parent is not None and parent.GetClass() == "FOOTPRINT":
            continue
        board.Remove(t)
        doomed.append(t)
    return doomed


def write_back(board, router):
    for net, layer, x1, y1, x2, y2, w in router.tracks:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(w))
        t.SetLayer(LAYER_ID[layer])
        t.SetNetCode(router.nets[net])
        board.Add(t)
    for net, x, y in router.vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(VIA_D))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNetCode(router.nets[net])
        board.Add(v)


def main():
    board = pcbnew.LoadBoard(BOARD)

    ds = board.GetDesignSettings()
    ds.m_MinClearance = pcbnew.FromMM(CLEAR)
    ds.m_TrackMinWidth = pcbnew.FromMM(0.25)

    _keep_alive = clear_routing(board)   # noqa: F841  -- see clear_routing()

    router = Router(board)
    todo = [n for n in router.pads if n != "GND" and len(router.pads[n]) > 1]

    def span(net):
        pts = router.pads[net]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5

    # Shortest first.  It is the order that leaves the most room: a short net has
    # almost no freedom, so it wants an empty board, while a long one can always
    # find a way round.  Measured against the alternatives (widest-first, longest-
    # first, and every combination), this one produced 4 failures where the rest
    # produced 10-14, and route_all() repairs the remainder.
    todo.sort(key=lambda n: span(n))

    print(f"grid {NX}x{NY}x{NL}  ({GRID} mm)   nets to route: {len(todo)}")
    failed = route_all(router, todo)

    for net in todo:
        w = WIDTHS.get(net, DEFAULT_W)
        n_t = sum(1 for t in router.tracks if t[0] == net)
        n_v = sum(1 for v in router.vias if v[0] == net)
        print(f"  [{'OK ' if net not in failed else 'FAIL'}] {net:<12} w={w:.2f}  "
              f"{n_t:>2} segs  {n_v} via(s)")
    ok = not failed

    write_back(board, router)
    board.Save(BOARD)
    print(f"\ntracks={len(router.tracks)}  vias={len(router.vias)}")
    print("saved", BOARD)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
