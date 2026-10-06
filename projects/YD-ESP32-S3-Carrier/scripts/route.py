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

INCREMENTAL (below) is the mode this board now needs: the copper already on the
board is kept untouched, becomes an obstacle, and counts as already-connected for
its own net, so only the new pads of the nets named in ONLY get laid down.  See
the note there for why the from-scratch pass no longer converges.
"""
import heapq
import math
import os
import sys

import numpy as np
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

BOARD_W, BOARD_H = 100.0, 74.0

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
# mm-equivalent charged for a layer change.  Overridable because on the 595 strip
# it is a *strategy* knob, not a constant: the empty band under the old board edge
# is ~9 mm tall and 98 mm wide on B.Cu and every net routed alone stayed on F.Cu,
# so the price of a via is what decides whether 31 new nets share one layer or two.
VIA_COST = float(os.environ.get("VIA_COST", "6.0"))

# Congestion.  A hard blocked mask is enough to keep two nets apart, but it gives
# A* no reason to prefer the empty half of the board over the millimetre next to
# copper it just laid -- so on the 595 strip every net routed along the same
# straight F.Cu line and later ones were walled out of a strip that measures 98 mm
# of empty B.Cu.  Charging a little for every grid step spent near existing copper
# turns that into a preference without ever making a legal cell illegal.
#
# CROWD_COST is mm charged per grid step of crowding (0 disables it entirely);
# CROWD_SPREAD is how far past the hard clearance the deterrent reaches.
CROWD_COST = float(os.environ.get("CROWD_COST", "0.0"))
CROWD_SPREAD = float(os.environ.get("CROWD_SPREAD", "0.60"))
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
#
# The second box is vestigial and deliberately kept: it describes the plug's
# overmould passing over y 64..68 inside a 74 mm outline, which was true when the
# board grew south but the sockets had not moved with it, and it stops at 68 because
# J8/J10 then ran through x 20..30.  The sockets have since slid to 18.80, so the
# body ends at 74.05 and the plug overhangs nothing -- and J8/J10 sit at x 50..98.
# It is left in place only because the shipped routing was laid under it, and
# deleting it would free a band for the router to reach into and produce a different
# board.  pour.py's matching box has been removed, because a stitch via costs
# nothing to add and the plane is better for it.
VIA_BAN = [(43.0, 11.0, 74.0, 32.0), (18.0, 60.0, 30.0, 68.0)]

# Rectangles no trace and no via of a routed net may enter -- a hole punched in
# the copper for the pour to flow through.
#
# The router cannot see zones (route.py runs first, pour.py second), so it will
# cheerfully wall a GND pad off: a ring of traces around one, each legal on its
# own, leaves the pour inside the ring an island.  J4.7 (82.000, 46.240) is the
# case that got through -- IO14's B.Cu jog (82.800,47.400)-(80.200,47.400) sits
# directly under the pad and 16.6 mm2 of pour is stranded behind it, on both
# layers, with every escape corridor measured and found blocked.  The pour has to
# be able to reach the pad from somewhere, so the only way to promise it is to
# tell the router where it may not go.
#
#   TRACE_BAN=x0:y0:x1:y1[,x0:y0:x1:y1...]     coordinates in mm
#
# Empty by default: this is not a general routing rule, it is a per-board
# instruction, and a box that is right for one board is a hole in the plane for
# another.  A GND *stitch via* in the box is harmless and in fact welcome -- it is
# part of the pour and welds the two sides together; only the routed nets are
# excluded.
TRACE_BAN = []
_ban_env = os.environ.get("TRACE_BAN")
if _ban_env:
    for _r in _ban_env.split(","):
        TRACE_BAN.append(tuple(float(_v) for _v in _r.split(":")))

# -- incremental mode ---------------------------------------------------------
# With INCREMENTAL on, every track and via already on the board is kept exactly
# where it is, becomes an obstacle, and counts as already-connected for its own
# net; only the nets named in ONLY are laid down again, and of those only the pads
# the existing copper does not already reach.  Nothing on the board is deleted.
#
# An earlier cut of this mode deleted the copper of every net named in ONLY before
# re-laying it.  That was wrong twice over, and measurably so: it threw away
# working copper the router then could not put back (+3V3, IO10 and IO12 were
# stranded by exactly that), and the deleted copper had itself been part of the
# answer, since a net's own existing run is a far better thing to aim at than the
# nearest pad, which can be 30 mm away on the wrong side of the board.
#
# Why this exists.  The from-scratch pass converges on the 100x64 board with 40
# nets and does *not* converge on the 100x74 one with 74: measured, it strands 20
# nets, and the casualties include +3V3 (0.80 mm) and +5V (1.00 mm).  Those two
# were always the tightest thing on the board -- too wide to pass between header
# pins, so they have to go the long way round -- and 34 new nets plus a strip full
# of new pads is what tipped them over.  That is congestion, not a bug.  But the
# panel drivers do not require re-deriving copper that already works, and
# re-deriving it is exactly what lost.  Incremental is also what a person would
# do: route the new part, leave the rest alone.
#
# ONLY must list every net that gained a pad.  +3V3 and IO9-IO12 count: they were
# routed before, but their new pads still have to reach the old run.
INCREMENTAL = True
ONLY = (
    ["ROW%d" % i for i in range(21)] +
    ["CSEL%d" % i for i in range(10)] +
    ["DRV_CASC1", "DRV_CASC2", "DRV_CASC3",
     "+3V3", "IO9", "IO10", "IO11", "IO12"]
)

# Diagnostic only: ONLY_SET=ROW0,ROW1,... narrows the pass to a chosen subset, so
# the strip can be measured on its own without the control nets competing for the
# same choke.  Unset in normal use.
_only_env = os.environ.get("ONLY_SET")
if _only_env:
    ONLY = tuple(_only_env.split(","))

# Repair budget.  The rip-up window is skipped whenever more than BLOCK_LIMIT nets
# sit around the failing pad -- on the strip that is almost every failure, so the
# last-resort loop (bare the board, lay the straggler first, rebuild on top) is
# what actually clears them, and it can only give one straggler a turn per round.
# 4 rounds cannot clear 20 stragglers, so ROUNDS defaults higher here.
ROUNDS = int(os.environ.get("ROUNDS", "4"))
BLOCK_LIMIT = int(os.environ.get("BLOCK_LIMIT", "10"))

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


def raster_seg_f(acc, layer, x1, y1, x2, y2, r, amount):
    """raster_seg, but accumulating a float cost instead of setting a flag.

    Same geometry, deliberately: the congestion field has to be the hard mask's
    own halo widened, or the router ends up paying for cells that are in fact
    clear, and avoiding cells it is not allowed to enter anyway.
    """
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
    acc[layer, i0:i1, j0:j1] += amount * (d <= r)


def raster_circle_f(acc, layer, cx, cy, r, amount):
    """raster_circle, accumulating a float cost."""
    i0, i1 = max(0, gi(cx - r) - 1), min(NX, gi(cx + r) + 2)
    j0, j1 = max(0, gj(cy - r) - 1), min(NY, gj(cy + r) + 2)
    if i0 >= i1 or j0 >= j1:
        return
    xs = (np.arange(i0, i1) * GRID)[:, None] - cx
    ys = (np.arange(j0, j1) * GRID)[None, :] - cy
    acc[layer, i0:i1, j0:j1] += amount * (np.hypot(xs, ys) <= r)


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


def reachable(mask, starts):
    """Which cells of `mask` are 4-connected to any of `starts`, per layer.

    Used to tell "this pad sits on the net's copper" from "this pad sits on *some*
    copper of this net".  Those are the same statement only while the net's
    pre-existing routing is a single connected piece, and on this board it very
    often is not: +3V3's old copper is several unjoined islands, and testing mere
    proximity to any of them marked pads "already connected" that had no path back
    to anything, so route_net() returned success on a net DRC still reported in
    pieces.  Copper is thin, so the walk visits only copper cells, not the board.
    """
    seen = np.zeros_like(mask)
    stack = []
    for (i, j, l) in starts:
        if mask[l, i, j] and not seen[l, i, j]:
            seen[l, i, j] = True
            stack.append((l, i, j))
    while stack:
        l, i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            i2, j2 = i + di, j + dj
            if not (0 <= i2 < NX and 0 <= j2 < NY):
                continue
            if mask[l, i2, j2] and not seen[l, i2, j2]:
                seen[l, i2, j2] = True
                stack.append((l, i2, j2))
    return seen


# ---------------------------------------------------------------------- router


class Router:
    def __init__(self, board):
        self.board = board
        self.shapes = collect_shapes(board)
        self.edge = edge_mask()
        self.tracks = []   # (net, layer, x1, y1, x2, y2, width)
        self.vias = []     # (net, x, y)
        # Copper that is already on the board and is to be left alone.  Deliberately
        # NOT in self.tracks: rip() lifts nets out of self.tracks by name, and a net
        # that is merely *in the way* can perfectly well be named as a rip-up victim
        # by blocking_nets().  Frozen copper is never a victim, so it must not be
        # reachable from there.  It is an obstacle in blocked_for() and a target in
        # route_net(); nothing else.
        self.frozen = []       # (net, layer, x1, y1, x2, y2, width)
        self.frozen_vias = []  # (net, x, y)
        self.fail_at = None   # pad the last route_net() could not reach, if any
        # Soft cost field: how much copper is already near each cell.  Rebuilt
        # lazily from self.tracks + self.frozen whenever they change, so it can
        # never drift out of step with the board the way a running total would
        # across rip/unrip.  Router-local and diagnostic-only -- it prices a
        # route, it never forbids one.
        self.crowd = np.zeros((NL, NX, NY), dtype=np.float32)
        self.crowd_dirty = True
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

        for onet, layer, x1, y1, x2, y2, w in self.tracks + self.frozen:
            if onet == net:
                continue
            raster_seg(m, layer, x1, y1, x2, y2, w / 2.0 + tr_r)
            raster_seg(v, layer, x1, y1, x2, y2, w / 2.0 + v_r)
        for vnet, vx, vy in self.vias + self.frozen_vias:
            if vnet == net:
                continue
            for layer in (0, 1):
                raster_circle(m, layer, vx, vy, VIA_D / 2.0 + tr_r)
                raster_circle(v, layer, vx, vy, VIA_D / 2.0 + v_r)

        # The pour throats, last and unconditional: a hole that a routed net can
        # close is not a hole.  This net's own pads are not exempt either -- a pad
        # inside the box is the pad the throat is for, and the pour reaches it
        # from outside the box.
        for layer in (0, 1):
            for x0, y0, x1, y1 in TRACE_BAN:
                raster_rect(m, layer, x0, y0, x1, y1, 0.0)
                raster_rect(v, layer, x0, y0, x1, y1, 0.0)
        return m, v

    def refresh_crowd(self):
        """Rebuild the congestion field from the copper the router currently holds.

        Frozen copper counts.  It is HEAD's routing, it is not going anywhere, and
        a cell beside it is exactly as expensive to squeeze past as one beside our
        own -- leaving it out is what let new runs hug the old ones.
        """
        if not self.crowd_dirty:
            return
        self.crowd[:] = 0.0
        for (net, layer, x1, y1, x2, y2, w) in self.tracks + self.frozen:
            raster_seg_f(self.crowd, layer, x1, y1, x2, y2,
                         w / 2.0 + CLEAR + CROWD_SPREAD, 1.0)
        for (vnet, vx, vy) in self.vias + self.frozen_vias:
            for layer in (0, 1):
                raster_circle_f(self.crowd, layer, vx, vy,
                                VIA_D / 2.0 + CLEAR + CROWD_SPREAD, 1.0)
        self.crowd_dirty = False

    def via_ok(self, x, y):
        for x0, y0, x1, y1 in VIA_BAN:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return False
        return True

    # -- A* ----------------------------------------------------------------
    def astar(self, blocked, via_blocked, starts, goals, vias_banned=False,
              crowd=None):
        """starts: [(i,j,layer)];  goals: bool array (NL,NX,NY).

        Returns a list of (i,j,layer) from a start to some goal node, or None.
        `blocked` gates movement along a layer; `via_blocked` gates a layer change,
        which has to clear both layers by the via's own radius.

        `crowd`, when given, adds CROWD_COST per grid step spent in a cell near
        existing copper.  It only ever *adds* to an edge cost, never removes an
        edge, so h() below stays admissible and a route that exists without it
        still exists with it -- the field changes which route wins, not whether
        one is found.
        """
        total = NL * NX * NY
        blk = bytearray(blocked.reshape(-1).tobytes())
        vblk = bytearray(via_blocked.reshape(-1).tobytes())
        # Same flat indexing as blk/vblk: nk is a single number, so the 3-D field
        # has to be viewed flat too.  reshape on a C-contiguous array is a view.
        cr = None if crowd is None else crowd.reshape(-1)
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
                if cr is not None:
                    cg = cr[nk]
                    if cg:
                        ng += CROWD_COST * cg * (step / GRID)
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
                    if cr is not None and cr[nb]:
                        ng += CROWD_COST * cr[nb]
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
        # Incremental mode: this net's existing copper is already one connected
        # piece, so a new pad only has to *reach* it -- not chase whichever pad
        # happens to be nearest.  On a net like +3V3, whose old copper runs past
        # the new parts while its nearest pad is 30 mm away, that is the whole
        # difference between routing and not.
        # `near` is `conn` opened out by half a grid step.  Asking whether a pad is
        # already on the net's existing copper is a question about the pad's grid
        # nodes, and a 0.30 mm run's nodes stop 0.15 mm from its centreline -- on a
        # 1.70 mm header pad, nowhere near the nodes half a millimetre off centre.
        # `near` closes that gap.  `conn` itself stays exact: it is what A* lands on,
        # so a node in it has to be on the copper, not merely near it.
        near = np.zeros((NL, NX, NY), dtype=bool)
        for (onet, layer, x1, y1, x2, y2, w) in self.frozen:
            if onet == net:
                raster_seg(conn, layer, x1, y1, x2, y2, w / 2.0)
                raster_seg(near, layer, x1, y1, x2, y2, w / 2.0 + GRID / 2.0)
        for (vnet, vx, vy) in self.frozen_vias:
            if vnet == net:
                for layer in (0, 1):
                    raster_circle(conn, layer, vx, vy, VIA_D / 2.0)
                    raster_circle(near, layer, vx, vy, VIA_D / 2.0 + GRID / 2.0)

        # Incremental mode assumes pad 0 sits on the net's existing copper -- that
        # is what makes "a new pad only has to *reach* the run" true, and what lets
        # `conn` be cut down to pad 0's island a few lines below.
        #
        # A *moved* footprint breaks that assumption.  Its pads keep their order, so
        # when the leftmost one is the pad that moved it no longer touches the net's
        # copper: `reach` collapses to that single pad, `conn &= reach` throws the
        # whole existing run away, and the net is re-laid from scratch -- into
        # exactly the congestion the incremental pass exists to avoid.  Measured:
        # sliding J1/J2 10.8 mm south stranded IO10, +3V3 and +5V this way, each
        # reporting "cannot reach pad" on a pad that had not moved at all.
        #
        # So the anchor is whichever pad the old run already touches.  `near` is the
        # test rather than `conn`, for the reason it is used below: a pad joins the
        # copper if its *grid nodes* reach it, and a 0.30 mm run's nodes stop
        # 0.15 mm short of its centreline.
        for a, (_, _, nodes, layers) in enumerate(pads):
            if any(near[l, i, j] for l in (layers or (0, 1)) for (i, j) in nodes):
                if a:
                    pads = [pads[a]] + pads[:a] + pads[a + 1:]
                    land(pads[0], conn)
                break

        # A pad already joined to pad 0 needs nothing done to it.  On the first pass
        # that is every pre-existing pad of a net that merely gained one -- the last
        # thing the board needs is a stub from each old pad to the run it is already
        # part of.  On a re-run it is every pad, which makes the pass idempotent
        # instead of a second helping of copper.
        #
        # "Joined to pad 0", not "near this net's copper": see reachable().  The
        # distinction is invisible while the net is one connected piece and decisive
        # when it is not, which on this board is the common case -- a pad stranded on
        # a distant island used to be marked taken and never routed, leaving the net
        # split with route_net() reporting success.
        #
        # `near` opens the copper out by half a grid step and is still the test used
        # here, because the question is whether the pad's *grid nodes* land on the
        # copper, and a thin run's nodes stop short of its centreline.  What changed
        # is which copper: only the part of it reachable from pad 0.
        reach = reachable(conn, [(i, j, l) for l in (pads[0][3] or (0, 1))
                                 for (i, j) in pads[0][2]])
        # The rasterisation above put *every* island of this net's copper into
        # `conn`, while `reach` -- correctly -- holds only the island pad 0 is on.
        # A* lands on `conn`, so leaving it whole makes the two disagree in exactly
        # the case that matters: when pads[0] is the *isolated* pad.  pads[0] sorts
        # first by x, which on this board used to be J8.1/J8.2/... at x = 2..9.6 mm
        # and is now the panel header at x = 50 mm; either way A* from a pad on the
        # real fragment finds its own start node already "in the target" and
        # returns a one-point path.  emit() lays no copper for a one-point path, yet
        # the pad is marked taken -- so route_net() reports [OK] with 0 segs on a
        # net DRC still lists as split.  The anchor chosen above is the primary
        # defence; this cut is the belt to that brace, and stays for the case where
        # a net has no old copper to anchor on at all.
        # Cutting `conn` down to `reach` makes the target exactly the set `taken`
        # reasons about; it grows from there as pads are hooked on.
        conn &= reach
        taken = [False] * len(pads)
        for a, (_, _, nodes, layers) in enumerate(pads):
            taken[a] = a == 0 or any(reach[l, i, j] and near[l, i, j]
                                     for l in (layers or (0, 1))
                                     for (i, j) in nodes)
        done = sum(taken)
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
            # Off by default, and skipped rather than passed as a zero field: a
            # non-uniform edge cost weakens h() enough that A* stops behaving like
            # a shortest-path search and starts behaving like a flood -- on this
            # board a 39-net pass went from ~2 minutes to over 15 at CROWD_COST
            # 0.04.  Worth it only when route quality matters more than runtime.
            field = None
            if CROWD_COST > 0.0:
                self.refresh_crowd()
                field = self.crowd
            path = self.astar(blocked, via_blocked, starts, conn, crowd=field)
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
        self.crowd_dirty = True
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
    router.crowd_dirty = True
    return gone


def unrip(router, saved):
    """Put ripped copper back exactly as it was -- same list, same order."""
    for item in saved:
        (router.tracks if len(item) == 7 else router.vias).append(item)
    router.crowd_dirty = True


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


def route_all(router, todo, radii=(5.0, 10.0, 18.0, 28.0), rounds=None):
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
    if rounds is None:
        rounds = ROUNDS
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
            victims = (blocking_nets(router, net, at, radius, limit=BLOCK_LIMIT)
                       if at else None)
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
    # find that.  Clear the board, lay the stragglers down first, then rebuild
    # everything else on top of them.
    #
    # One net is promoted per round, and the rounds rotate which one.  Promoting the
    # whole failure set instead -- which is the obvious reading of "they all route
    # alone, let them all go first" -- was tried and is measurably worse (18 routed
    # against 23): the corridor is 213 lanes wide for 39 nets (_probe_throat.py), so
    # it is not the space that runs out, it is that laying 17 nets down before the
    # other 22 fragments the board into pockets too small for a greedy A* to thread.
    # Privileging one net moves the pinch to a different net cheaply; privileging all
    # of them at once is just a different greedy order, and a worse one.
    #
    # Two things the loop does now that it did not:
    #
    #   * `best` is seeded with the board as the repair pass left it, so the last
    #     resort can only ever improve on that.  It used to keep whatever the final
    #     trial produced -- and since a rebuild can strand a different net, a run
    #     that had 23 nets routed at the top of this loop could walk out with 18.
    #   * every trial is scored and the best kept, rather than the last one winning
    #     by default.
    best = (len(todo) - len(failed), list(failed),
            list(router.tracks), list(router.vias))
    for _ in range(rounds):
        if not failed:
            break
        star = failed[0]
        others = [n for n in todo if n != star]
        saved = rip(router, set(todo))            # board bare
        if not router.route_net(star):
            rip(router, {star})                   # drop the partial attempt
            unrip(router, saved)                  # and put the real board back
            failed = failed[1:] + [star]          # let the next one have a turn
            continue
        still = [n for n in others if not router.route_net(n)]
        score = len(todo) - len(still)
        if score > best[0]:
            best = (score, list(still), list(router.tracks), list(router.vias))
        if not still:
            failed = []
            break
        failed = still[1:] + still[:1]            # a different net leads next round

    _score, failed, router.tracks, router.vias = best

    # A net that never finished leaves partial copper behind, which reads on the
    # board as a half-connected net.  Strip it: the rest of the routing was laid
    # down *around* that copper, so removing it can only free space, never collide.
    rip(router, set(failed))
    return failed


# ------------------------------------------------------------------- to board


def absorb(board, router):
    """Read the board's own copper into the router as frozen.

    The board is already routed and that routing works.  Re-deriving it is exactly
    what the from-scratch pass fails at, so this touches nothing: it records every
    track and via, which makes them obstacles in blocked_for() and connection
    targets in route_net().  The new pads of a net that already existed then only
    have to *reach* that net's old run.

    Nothing is removed, and in particular the nets named in ONLY keep their copper.
    See the note on INCREMENTAL for why deleting it was not just destructive but
    counter-productive.

    Footprint-owned items are skipped for the same reason clear_routing() leaves
    them: they belong to the footprint, and U1's thermal vias are not ours to move.
    """
    for t in list(board.GetTracks()):
        parent = t.GetParent()
        if parent is not None and parent.GetClass() == "FOOTPRINT":
            continue
        net = t.GetNetname()
        s, e = t.GetStart(), t.GetEnd()
        x1, y1 = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
        x2, y2 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
        if t.GetClass() == "PCB_VIA":
            router.frozen_vias.append((net, x1, y1))
        elif t.GetLayer() == pcbnew.F_Cu:
            router.frozen.append((net, 0, x1, y1, x2, y2,
                                  pcbnew.ToMM(t.GetWidth())))
        elif t.GetLayer() == pcbnew.B_Cu:
            router.frozen.append((net, 1, x1, y1, x2, y2,
                                  pcbnew.ToMM(t.GetWidth())))


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

    if not INCREMENTAL:
        _keep_alive = clear_routing(board)   # noqa: F841  -- see clear_routing()

    router = Router(board)

    if INCREMENTAL:
        if not ONLY:
            sys.exit("INCREMENTAL is on but ONLY is empty: an incremental pass has "
                     "to name the nets it is laying down, or the whole board gets "
                     "re-routed on top of itself.")
        absorb(board, router)
        print(f"kept {len(router.frozen)} track(s) / {len(router.frozen_vias)} "
              f"via(s) already on the board, untouched; "
              f"{len(ONLY)} net(s) may gain copper")

    todo = [n for n in router.pads if n != "GND" and len(router.pads[n]) > 1]
    if INCREMENTAL:
        todo = [n for n in todo if n in ONLY]
        missing = sorted(set(ONLY) - set(todo))
        if missing:
            sys.exit("ONLY names net(s) with nothing to route on this board: "
                     + ", ".join(missing))

    def span(net):
        pts = router.pads[net]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5

    # Shortest first.  It is the order that leaves the most room: a short net has
    # almost no freedom, so it wants an empty board, while a long one can always
    # find a way round.  Measured against the alternatives (widest-first, longest-
    # first, and every combination) on the pre-595 board, this one produced 4
    # failures where the rest produced 10-14, and route_all() repairs the rest.
    #
    # That measurement is from before the strip existed.  The strip puts every
    # panel net through one narrow gate in x, where short-first is backwards: a
    # short net that grabs a lane costs a long net its only way west.  ORDER=long
    # tests that; ORDER=none takes the file's order.
    ORDER = os.environ.get("ORDER", "span")
    if ORDER == "long":
        todo.sort(key=lambda n: -span(n))
    elif ORDER == "none":
        pass
    elif ORDER == "lane":
        # The 595 outputs are a *bus*, not a bag of nets: U3..U6 sit east of the
        # header field and their pins map to J8/J10 almost monotonically, so the
        # 31 runs want to lie side by side like a ribbon, each one turning down
        # into its own pin.  Sorting by the header-side x (the net's smallest pad
        # x) hands A* the nets in the order their lanes are stacked, so each one
        # takes the lane it is actually meant to have instead of the shortest
        # one it can grab -- which is what pins a later net against a wall with
        # no way round.
        todo.sort(key=lambda n: min(p[0] for p in router.pads[n]))
    elif ORDER == "lane-rev":
        todo.sort(key=lambda n: -min(p[0] for p in router.pads[n]))
    else:
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
