"""Flood, not A*: how far can an edge header pin actually reach?

The A* feasibility run came back 0/20 on both headers with the search frontier
pinned at a constant column -- which is either a real seal or a grid artefact,
and those two need opposite responses. A flood settles it: no heuristic, no
goal set, no way to "fail to find a path". If the reachable set is bounded,
the bound is the answer and the frontier's owners name the walls. If it spans
the board, the A* result was the artefact and the architecture is fine.

Everything the real plan would do is done here, in memory, in order:

  1. widen the outline x 100..171 -> 90..181
  2. load and place J1A (left edge) and J1B (right edge)
  3. rip the copper that only existed to feed the old bottom-centre FPC
  4. build the router's own clearance model over what is left
  5. flood every probe pin and report reach, bbox, and frontier owners

and it prints a census of step 3 first, because a rip that eats the row trunks
makes step 5 meaningless -- the reach would be huge and wrong.

    python edgeflood.py <board> [--step 0.1] [--safety 0.04] [--pins 1,10,20]
                        [--no-widen] [--no-rip] [--no-place]
"""

import argparse
from collections import Counter, deque

import numpy as np
import pcbnew

from probe import NGrid, astar, TRACK_W, VIA_DIA
from replan import Router, cells_of, pad_cells

S = 1e6

#: Boards removed with board.Remove() are handed to Python, and once ~10 of
#: those proxies are collected SWIG drops its process-wide type registry and
#: the next LoadBoard returns a bare SwigPyObject. See replan/cor1.txt. Every
#: removed item has to stay reachable for the life of the process.
GRAVE = []

HDR_LIB = ("C:/Program Files/KiCad/10.0/share/kicad/footprints/"
           "Connector_PinHeader_2.54mm.pretty")
HDR_FP = "PinHeader_1x20_P2.54mm_Vertical"

#: Outline after widening -- +10mm on each side, height untouched.
WIDEN_X0, WIDEN_X1 = 90.0, 181.0
#: Header centres. Pad radius 0.85mm: the copper-to-edge rule (0.5mm) puts the
#: left centre no closer than 91.35, and the 5mm electrodes start at 104.20.
LEFT_X, RIGHT_X = 95.4, 175.6
LEFT_Y, RIGHT_Y = 115.67, 180.97

#: The electrode array's copper extent, from recon.py.
ELEC_X0, ELEC_X1 = 104.20, 166.80
#: Nothing below the electrodes but the old FPC fan-out.
BOTTOM_Y = 241.50

#: The approved pin allocation. ROW3 / ROW5 sit on pin 1 and pin 20 of J1A,
#: i.e. the two ends of the same connector, per the user's choice -- and they
#: are routed first, which is the standing instruction behind task #4.
ASSIGN = {
    "J1A": {1: "ROW3", 2: "ROW0", 3: "ROW1", 4: "ROW2", 5: "ROW4",
            6: "ROW6", 7: "ROW7", 8: "ROW8", 9: "ROW9", 10: "ROW10",
            11: "CSEL0", 12: "CSEL1", 13: "CSEL2", 14: "CSEL3",
            15: "CSEL4", 16: "GND", 17: "GND", 18: "+3V3", 19: "+3V3",
            20: "ROW5"},
    "J1B": {1: "ROW11", 2: "ROW12", 3: "ROW13", 4: "ROW14", 5: "ROW15",
            6: "ROW16", 7: "ROW17", 8: "ROW18", 9: "ROW19", 10: "ROW20",
            11: "CSEL5", 12: "CSEL6", 13: "CSEL7", 14: "CSEL8",
            15: "CSEL9", 16: "GND", 17: "GND", 18: "GND", 19: "+3V3",
            20: "+3V3"},
}


def widen(board):
    """Map every Edge.Cuts endpoint off the old verticals onto the new ones.

    The outline is four plain segments, x 100..171 by y 100..250 -- and it has
    to stay a *closed* loop. Moving only the two vertical edges leaves the two
    horizontal ones still spanning 100..171, so the corners come apart and DRC
    reports ``invalid_outline: 4``. Remapping x on every endpoint, horizontal
    and vertical alike, stretches the horizontals to match.
    """
    def remap(x):
        v = x / S
        if abs(v - 100.0) < 0.5:
            return int(WIDEN_X0 * S)
        if abs(v - 171.0) < 0.5:
            return int(WIDEN_X1 * S)
        return x

    moved = 0
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        try:
            s, e = d.GetStart(), d.GetEnd()
        except AttributeError:
            continue
        ns, ne = remap(s.x), remap(e.x)
        if ns == s.x and ne == e.x:
            continue
        d.SetStart(pcbnew.VECTOR2I(ns, s.y))
        d.SetEnd(pcbnew.VECTOR2I(ne, e.y))
        moved += 1
    return moved


def net_of(board, name):
    """The board's NETINFO_ITEM for `name`, created if this net is new."""
    net = board.FindNet(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def place(board, ref, lib, name, x, y, assign=None):
    """Drop a footprint in and give its pads their nets.

    `FootprintLoad` leaves every pad on net 0, and that matters for more than
    tidiness: a pad with no net reads netname "" and lands in the *obstacle*
    set of every net_grid() call, walling in the very pin being routed from.
    The real board gets its nets from `sync_schematic_to_board`, so assigning
    them here is only making the in-memory model say what the file will say.
    """
    fp = pcbnew.FootprintLoad(lib, name)
    if fp is None:
        raise SystemExit(f"FootprintLoad failed for {name}")
    fp.SetReference(ref)
    fp.SetPosition(pcbnew.VECTOR2I(int(x * S), int(y * S)))
    if assign:
        for pad in fp.Pads():
            try:
                pin = int(pad.GetNumber())
            except ValueError:
                continue
            nm = assign.get(pin)
            if nm:
                pad.SetNet(net_of(board, nm))
    board.Add(fp)
    return fp


def anchors_of(board, skip=("J1",)):
    """netname -> [(x, y)] of every pad that is allowed to hold copper in place.

    J1's pads are deliberately excluded: they belong to the connector being
    deleted, so treating them as anchors would spare the entire fan-out -- the
    exact copper the rip exists to remove. This is not hypothetical; the first
    version of the rip had no anchor rule at all and the reason it was added is
    the mirror image of the same mistake (see ``anchored``).
    """
    out = {}
    for fp in board.GetFootprints():
        if fp.GetReference() in skip:
            continue
        for p in fp.Pads():
            n = p.GetNetname()
            if not n:
                continue
            pos = p.GetPosition()
            out.setdefault(n, []).append((pos.x / S, pos.y / S))
    return out


def anchored(t, anchors, tol=0.20):
    """Does this segment terminate on a pad of its own net?

    The bbox test alone is too blunt at the sides. Each pull-down R1-R21
    reaches its row trunk through one short F.Cu segment that starts on the
    resistor pad at x=101.59 and ends on the trunk at x=103.84 -- e.g. R4 on
    ROW3 is ``101.59,127.00 -> 103.71,129.12``. That segment lies wholly inside
    the left gutter, so a region-only rip deletes it and orphans R4.1; the A*
    test then "succeeds" by landing on the orphan, which is a false positive
    (measured: ROW3 came back as 3 components, the third being R4.1's pad).

    The discriminator is that a live link touches a pad and a fan-out run does
    not: J1 is at the bottom centre, so no fan-out segment has an endpoint on a
    component pad except where it merges into its own trunk, and the trunk is
    not in a rip region.
    """
    pts = anchors.get(t.GetNetname())
    if not pts:
        return False
    for e in (t.GetStart(), t.GetEnd()):
        ex, ey = e.x / S, e.y / S
        for px, py in pts:
            if abs(ex - px) <= tol and abs(ey - py) <= tol:
                return True
    return False


def rip(board, anchors, keep_nets=frozenset()):
    """Remove the copper that fed the bottom-centre FPC.

    Three regions, because those are the three places the 0.5mm FPC fan-out
    put copper that a side header makes redundant: the bottom strip below the
    electrodes, and the two side gutters. The test is on each segment's own
    bounding box -- a segment that *reaches into* a gutter from the interior is
    interior copper and stays -- minus the pad-anchored links ``anchored``
    describes, which are live connections that merely happen to sit in a gutter.

    ``keep_nets`` is the safety catch, and it is the difference between a rip
    and a demolition. On this board the J1 fan-out is not merely a fan-out: it
    *is* the distribution network, so cutting it fragments the net rather than
    just unhooking the connector. That is recoverable where the net has a
    header pin to be re-fed from -- but COL0..COL9 have no pin at all (they are
    the internal column returns, deliberately not brought out). Ripping them
    turned COL0 into 22 islands that nothing can ever rejoin. Nets with no
    header pin are therefore excluded outright.

    Returns (ripped, spared).
    """
    out = []
    spared = 0
    for t in list(board.GetTracks()):
        net = t.GetNetname()
        if net in keep_nets:
            continue
        bb = t.GetBoundingBox()
        x0, y0 = bb.GetLeft() / S, bb.GetTop() / S
        x1, y1 = bb.GetRight() / S, bb.GetBottom() / S
        if not (y0 > BOTTOM_Y or x1 < ELEC_X0 or x0 > ELEC_X1):
            continue
        if anchored(t, anchors):
            spared += 1
            continue
        board.Remove(t)
        GRAVE.append(t)
        out.append((net, x0, y0, x1, y1))
    return out, spared


def rip_spur(board, root="J1", tol=0.15, keep_nets=frozenset()):
    """Delete the copper that *hangs off* `root`, and nothing else.

    The region rip asks "is this segment in a gutter?", which is the wrong
    question: plenty of copper in those regions does not belong to the
    connector at all, it is some other net's distribution network that happens
    to run through. Cutting that split 102 nets.

    The question that matches the intent is "does this segment hang off the
    connector?". So walk the copper graph out from `root`'s pads, and stop at
    every other component's pad. What you delete is then a set of spurs, each
    rooted on a pin and terminating on real copper -- and every net keeps its
    trunk, its pull-down and its gate wiring, which is all it needs to be
    re-fed from a side header.

    Vias are PCB_TRACKs with start == end, so they sit on the path and are
    traversed (and ripped) like any other segment.

    Returns (ripped, roots, spared_at_pads).
    """
    def key(x, y):
        return (round(x, 2), round(y, 2))

    # A pad that is not the root's is a *terminator*: the spur ends there, and
    # whatever continues on the far side belongs to that component, not us.
    stops = []
    for fp in board.GetFootprints():
        if fp.GetReference() == root:
            continue
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            stops.append((bb.GetLeft() / S - tol, bb.GetTop() / S - tol,
                          bb.GetRight() / S + tol, bb.GetBottom() / S + tol))

    def stopped(x, y):
        return any(a <= x <= c and b <= y <= d for a, b, c, d in stops)

    roots_at = []
    for fp in board.GetFootprints():
        if fp.GetReference() != root:
            continue
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            roots_at.append((bb.GetLeft() / S - tol, bb.GetTop() / S - tol,
                             bb.GetRight() / S + tol, bb.GetBottom() / S + tol))

    def is_root(x, y):
        return any(a <= x <= c and b <= y <= d for a, b, c, d in roots_at)

    segs = list(board.GetTracks())
    ends = []
    by_pt = {}
    for no, t in enumerate(segs):
        s, e = t.GetStart(), t.GetEnd()
        a = (s.x / S, s.y / S)
        b = (e.x / S, e.y / S)
        ends.append((a, b))
        by_pt.setdefault(key(*a), []).append(no)
        by_pt.setdefault(key(*b), []).append(no)

    seen, queue, roots = set(), deque(), 0
    for no, (a, b) in enumerate(ends):
        if is_root(*a) or is_root(*b):
            roots += 1
            if no not in seen:
                seen.add(no)
                queue.append(no)

    while queue:
        no = queue.popleft()
        for pt in ends[no]:
            if stopped(*pt):        # this spur ends on someone else's pad
                continue
            for nxt in by_pt.get(key(*pt), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)

    out = []
    for no in seen:
        t = segs[no]
        if t.GetNetname() in keep_nets:
            continue
        s, e = t.GetStart(), t.GetEnd()
        out.append((t.GetNetname(), s.x / S, s.y / S, e.x / S, e.y / S))
        board.Remove(t)
        GRAVE.append(t)
    return out, roots, len(stops)


def census(items, title):
    if not items:
        print(f"  {title}: none")
        return
    by = Counter(n for n, *_ in items)
    print(f"  {title}: {len(items)} segment(s) over {len(by)} net(s)")
    for net, c in sorted(by.items(), key=lambda t: (-t[1], t[0]))[:14]:
        xs0 = min(i[1] for i in items if i[0] == net)
        xs1 = max(i[3] for i in items if i[0] == net)
        ys0 = min(i[2] for i in items if i[0] == net)
        ys1 = max(i[4] for i in items if i[0] == net)
        print(f"      {net:<7} {c:4d}  x {xs0:7.2f}..{xs1:7.2f}  "
              f"y {ys0:7.2f}..{ys1:7.2f}")
    if len(by) > 14:
        print(f"      ... and {len(by) - 14} more net(s)")


def net_copper(board, want):
    """(count, y_min, y_max, x_min, x_max) of a net's surviving tracks."""
    ts = [t for t in board.GetTracks() if t.GetNetname() == want]
    if not ts:
        return 0, None, None, None, None
    ys = [t.GetPosition().y / S for t in ts] + [t.GetEnd().y / S for t in ts]
    xs = [t.GetPosition().x / S for t in ts] + [t.GetEnd().x / S for t in ts]
    return len(ts), min(ys), max(ys), min(xs), max(xs)


def flood(grid, seeds, cap_cells=4_000_000):
    """BFS over legal cells incl. vias. Returns {layer: seen mask}."""
    layers = grid.layers
    li = {l: k for k, l in enumerate(layers)}
    ny, nx = grid.ny, grid.nx
    OK, VOK = grid.OK, grid.VOK
    seen = np.zeros((len(layers), ny, nx), bool)
    q = deque()
    for lay, i, j in seeds:
        if not (0 <= i < nx and 0 <= j < ny):
            continue
        if not seen[li[lay], j, i]:
            seen[li[lay], j, i] = True
            q.append((li[lay], i, j))
    NB = ((1, 0), (-1, 0), (0, 1), (0, -1),
          (1, 1), (1, -1), (-1, 1), (-1, -1))
    n = 0
    while q:
        k, i, j = q.popleft()
        n += 1
        if n > cap_cells:
            return seen, True
        ok = OK[layers[k]]
        for di, dj in NB:
            ni, nj = i + di, j + dj
            if 0 <= ni < nx and 0 <= nj < ny and ok[nj, ni] \
                    and not seen[k, nj, ni]:
                seen[k, nj, ni] = True
                q.append((k, ni, nj))
        if VOK[j, i]:
            for k2 in range(len(layers)):
                if k2 != k and not seen[k2, j, i] \
                        and OK[layers[k2]][j, i]:
                    seen[k2, j, i] = True
                    q.append((k2, i, j))
    return seen, False


def report(grid, board, seeds, names):
    seen, hit_cap = flood(grid, seeds)
    tot = int(seen.sum())
    if tot == 0:
        print("      reach: 0 cells -- the seed is walled in")
        return None
    print(f"      reach: {tot:,} cells on "
          f"{int(seen.reshape(len(grid.layers), -1).any(axis=1).sum())} "
          f"layer(s)" + ("  [CAP HIT]" if hit_cap else ""))
    for k, lay in enumerate(grid.layers):
        m = seen[k]
        if not m.any():
            continue
        jj, ii = np.nonzero(m)
        print(f"        {board.GetLayerName(lay):<5} {int(m.sum()):9,} cells  "
              f"x {grid.x0 + ii.min() * grid.step:7.2f}.."
              f"{grid.x0 + ii.max() * grid.step:7.2f}  "
              f"y {grid.y0 + jj.min() * grid.step:7.2f}.."
              f"{grid.y0 + jj.max() * grid.step:7.2f}")

    # Who is on the border of that region? Those are the walls, and their
    # names are the rip-up list. Only meaningful when the region is bounded,
    # which is exactly the case worth diagnosing.
    border = np.zeros_like(seen)
    for k in range(len(grid.layers)):
        m = seen[k]
        if not m.any():
            continue
        g = m.copy()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            g &= np.roll(np.roll(m, di, axis=0), dj, axis=1)
        border[k] = m & ~g
    own = Counter()
    for k, lay in enumerate(grid.layers):
        m = border[k]
        if not m.any():
            continue
        jj, ii = np.nonzero(m)
        for no in grid.OWN[lay][jj, ii]:
            if no >= 0:
                own[names[no]] += 1
    print("      frontier owners: " + (", ".join(
        f"{w} {c}" for w, c in own.most_common(9)) or "none (open board)"))
    return seen


def components(grid, names, board, layers, want=None):
    """Per-net connected components of surviving copper, in one pass.

    `D[lay] <= 0` is *inside* the copper -- the grid measures distance to the
    shape with the track radius already subtracted -- and OWN names the item
    that owns each cell, so labelling every copper cell by net and then
    grouping same-net neighbours gives the copper's connectivity directly.

    This is what turns "the route found a path" into "the route found a path to
    copper that is still on the net". Without it a rip that orphans a pull-down
    pad looks like a triumph, because the orphan is only 12mm from the header.

    Vias join the layers: the flood crosses at any cell where both layers have
    copper of the same net.
    """
    li = {l: k for k, l in enumerate(layers)}
    ny, nx = grid.ny, grid.nx
    # -1 = no copper, else the net index
    nid = np.full((len(layers), ny, nx), -1, np.int32)
    rev = {}
    for k, lay in enumerate(layers):
        m = grid.D[lay] <= 0
        if not m.any():
            continue
        own = grid.OWN[lay][m]
        lut = np.zeros(int(own.max()) + 1, np.int32)
        for no in np.unique(own):
            if no < 0 or not names[no]:
                continue
            nm = names[no]
            if nm not in rev:
                rev[nm] = len(rev) + 1
            lut[no] = rev[nm]
        nid[k][m] = lut[own]

    INV = {v: n for n, v in rev.items()}
    seen = np.zeros_like(nid, bool)
    out = {}
    NB = ((1, 0), (-1, 0), (0, 1), (0, -1),
          (1, 1), (1, -1), (-1, 1), (-1, -1))
    for k in range(len(layers)):
        for j, i in zip(*np.nonzero((nid[k] > 0) & ~seen[k])):
            # The index list is materialised once per layer, so every cell a
            # previous component already swallowed is still in it. Without
            # this guard each of those re-seeds as a 1-cell "component", and a
            # board where nothing is broken reports 253 fragmented nets.
            if seen[k, j, i]:
                continue
            v = nid[k, j, i]
            nm = INV[v]
            q = deque([(k, i, j)])
            seen[k, j, i] = True
            cnt = 0
            xs0 = xs1 = i
            ys0 = ys1 = j
            while q:
                kk, ii, jj = q.popleft()
                cnt += 1
                xs0, xs1 = min(xs0, ii), max(xs1, ii)
                ys0, ys1 = min(ys0, jj), max(ys1, jj)
                same = nid[kk] == v
                for di, dj in NB:
                    ni, nj = ii + di, jj + dj
                    if 0 <= ni < nx and 0 <= nj < ny and same[nj, ni] \
                            and not seen[kk, nj, ni]:
                        seen[kk, nj, ni] = True
                        q.append((kk, ni, nj))
                for k2 in range(len(layers)):
                    if k2 != kk and nid[k2, jj, ii] == v \
                            and not seen[k2, jj, ii]:
                        seen[k2, jj, ii] = True
                        q.append((k2, ii, jj))
            out.setdefault(nm, []).append(
                (cnt, grid.x0 + xs0 * grid.step, grid.y0 + ys0 * grid.step,
                 grid.x0 + xs1 * grid.step, grid.y0 + ys1 * grid.step))
    for v in out.values():
        v.sort(key=lambda c: -c[0])
    return out


def route_endpoint(grid, path):
    lay, i, j = path[-1]
    return grid.xy(i, j)


def own_items(board, net):
    """Every copper item on `net` -- the route's goals, and its anchors."""
    out = [t for t in board.GetTracks() if t.GetNetname() == net]
    for fp in board.GetFootprints():
        out += [p for p in fp.Pads() if p.GetNetname() == net]
    return out


def net_grid(board, net, proto, layers, skip=frozenset()):
    """A grid for one net's route, with that net's own copper left *legal*.

    Two rules, both copied from the router itself, and both load-bearing here.

    ``obstacles(exclude)`` drops the net it is routing, so every *other* net
    stays an obstacle. ``skip`` holds the header pads, and they have to be
    skipped rather than net-tested: `place()` never assigns them a net, so
    they read netname "" and land in the obstacle set -- where they wall in
    the very pad being routed from, which reports as "reach == seed count"
    and looks exactly like a sealed escape.

    Then the net's own copper must be marked legal on purpose. ``astar``
    expands only onto cells that are ``OK`` (probe.py, the ``if not
    OK[lay][nj, ni]: continue`` on the non-conflict path), and ``cells_of``
    samples a goal's *centreline* -- which in this fan-out lies inside the
    keep band of the track running parallel to it 0.4mm away. So the goal
    cell reads illegal, no legal cell is ever within reach of it, and the
    search stops one step short. That is the whole of the ``closest
    0.10-0.94mm`` face-on-miss cluster: a harness artefact, not a wall.

    Relaxing to ``D_own <= 0`` -- inside this net's own copper, the exact set
    the route is entitled to land on -- rather than to a whole keep band,
    keeps the clearance rule against every other net fully intact.
    """
    other = [t for t in board.GetTracks() if t.GetNetname() != net]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net and p.m_Uuid.AsString() not in skip:
                other.append(p)
    own = own_items(board, net)

    g = NGrid(board, proto.step, proto.keep, proto.edge_keep,
              proto.pad_keep, proto.via_edge_keep, layers)
    g.build(other)

    if own:
        gn = NGrid(board, proto.step, proto.keep, proto.edge_keep,
                   proto.pad_keep, proto.via_edge_keep, layers)
        gn.build(own)
        for lay in layers:
            g.OK[lay] |= (gn.D[lay] <= 0.0) & (g.EG >= g.edge_keep)

    names = []
    for it in other:
        try:
            names.append(it.GetNetname())
        except AttributeError:
            names.append("?")
    return g, names


def pad_box(pad, slack=0.05):
    """A pad's board-space bounding box, as (x0, y0, x1, y1) in mm."""
    bb = pad.GetBoundingBox()
    return (bb.GetLeft() / S - slack, bb.GetTop() / S - slack,
            bb.GetRight() / S + slack, bb.GetBottom() / S + slack)


def route(grid, board, seeds, net, layers, via_cost=25.0, exclude_pads=()):
    """A* from one header pin to the rest of `net`, and the honest fallback.

    A flood says the space is open; it does not say a path exists to a
    *particular* net's copper. This is the real test -- and when it fails, the
    useful number is not "no path" but how close the search got, because that
    distance is what a rip-up would have to buy back.

    ``exclude_pads`` is every header pad, and leaving it out makes the test
    lie. The header pads carry their nets now, so they are copper on `net` and
    join the goal set -- which means a pin routes 0.8mm to the pin next to it
    and reports success. For GND and +3V3, whose pins sit in adjacent pairs
    and triples, that is the *nearest* goal and always wins, so the route
    never has to reach the plane those pins are supposed to join. Dropping the
    header's own pads asks the question that matters instead: can this pin
    reach the rest of the design?
    """
    own = [t for t in board.GetTracks() if t.GetNetname() == net]
    for fp in board.GetFootprints():
        own += [p for p in fp.Pads() if p.GetNetname() == net]
    if not own:
        return None, None, "net has no copper left"
    goals = cells_of(grid, own, layers) - set(seeds)
    for pad in exclude_pads:
        x0, y0, x1, y1 = pad_box(pad)
        goals = {(l, i, j) for (l, i, j) in goals
                 if not (x0 <= grid.x0 + i * grid.step <= x1
                         and y0 <= grid.y0 + j * grid.step <= y1)}
    if not goals:
        return None, None, "net's copper is all inside the header pads"
    path, cross, exp, closest = astar(grid, seeds, goals, via_cost, False)
    if path:
        ln = sum(((path[k][1] - path[k - 1][1]) ** 2
                  + (path[k][2] - path[k - 1][2]) ** 2) ** 0.5
                 for k in range(1, len(path))) * grid.step
        return path, ln, None
    return None, closest, "no path"


def seg_dist(px, py, ax, ay, bx, by):
    """Distance from a point to the segment a-b."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def nearest_own(board, x, y, net):
    """What piece of `net`'s copper sits closest to (x, y)? Naming it is the
    difference between "the route worked" and "the route stopped on the first
    pad it tripped over".

    Distance is to the whole segment, not to its endpoints. A trunk is 60mm
    long, and an arrival cell sitting on its middle is 30mm from either end --
    measuring endpoint distance reports "6.7mm, nearest is a header pad" for a
    route that in fact landed squarely on the trunk it was aimed at.
    """
    best, who = 1e18, "?"
    for it in list(board.GetTracks()):
        if it.GetNetname() != net:
            continue
        s, e = it.GetStart(), it.GetEnd()
        d = seg_dist(x, y, s.x / S, s.y / S, e.x / S, e.y / S)
        if d < best:
            best, who = d, f"track {s.x/S:.2f},{s.y/S:.2f}->{e.x/S:.2f},{e.y/S:.2f}"
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            pp = p.GetPosition()
            d = ((pp.x / S - x) ** 2 + (pp.y / S - y) ** 2) ** 0.5
            if d < best:
                best, who = d, f"pad {fp.GetReference()}.{p.GetNumber()}"
    return best, who


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=float, default=0.1)
    ap.add_argument("--safety", type=float, default=0.04)
    ap.add_argument("--pins", default="1,10,20")
    ap.add_argument("--no-widen", action="store_true")
    ap.add_argument("--no-rip", action="store_true")
    ap.add_argument("--del-j1", action="store_true",
                    help="drop the J1 footprint too, so a route cannot claim "
                         "success by ending on a pad that is about to vanish")
    ap.add_argument("--spur", action="store_true",
                    help="rip only the copper hanging off J1 instead of "
                         "every segment in the gutters and bottom strip")
    ap.add_argument("--no-place", action="store_true")
    ap.add_argument("--route", default="",
                    help="comma list of nets to A* to (default: flood only)")
    ap.add_argument("--frag", default="",
                    help="report per-net copper components after the rip; "
                         "value is a comma list of extra nets to always show")
    ap.add_argument("--save", default="",
                    help="save the modified board here and stop (so kicad-cli "
                         "can be the judge of connectivity)")
    ap.add_argument("--emit", default="",
                    help="lay real copper. 'auto' measures every pin's "
                         "isolated path length on the pre-emit board and "
                         "routes the shortest-slack nets first, with ROW3/"
                         "ROW5 pinned to the front. Otherwise a priority list "
                         "such as 'ROW3,ROW5,J1A.14:CSEL3' that the remaining "
                         "pins follow in pin order ('all' = plain pin order)")
    ap.add_argument("--out", default="",
                    help="where --emit saves the routed board")
    ap.add_argument("--soft-radius", type=float, default=0.0,
                    help="charge for crowding within this radius (mm); 0=off")
    ap.add_argument("--soft-weight", type=float, default=6.0,
                    help="cost per grid step inside the crowding radius")
    a = ap.parse_args()
    pins = [p.strip() for p in a.pins.split(",")]

    board = pcbnew.LoadBoard(a.src)
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S

    bb = board.GetBoardEdgesBoundingBox()
    print(f"outline before: x {bb.GetLeft()/S:.3f}..{bb.GetRight()/S:.3f}  "
          f"y {bb.GetTop()/S:.3f}..{bb.GetBottom()/S:.3f}")

    hdr = {}
    if not a.no_place:
        for ref, x, y in (("J1A", LEFT_X, LEFT_Y), ("J1B", RIGHT_X, RIGHT_Y)):
            hdr[ref] = place(board, ref, HDR_LIB, HDR_FP, x, y, ASSIGN[ref])
        print(f"placed J1A @({LEFT_X},{LEFT_Y})  J1B @({RIGHT_X},{RIGHT_Y})")

    if not a.no_widen:
        print(f"widened {widen(board)} vertical edge(s)")
        bb = board.GetBoardEdgesBoundingBox()
        print(f"outline after : x {bb.GetLeft()/S:.3f}..{bb.GetRight()/S:.3f}  "
              f"y {bb.GetTop()/S:.3f}..{bb.GetBottom()/S:.3f}")

    if not a.no_rip:
        print("\nrip -- copper that only fed the bottom-centre FPC:")
        anchors = anchors_of(board)
        # COL0..COL9 have no header pin, so copper the rip cuts off them can
        # never be reconnected. Compute the pinless set rather than hard-coding
        # it, so the rule still holds if the allocation changes.
        pinned = {n for pins in ASSIGN.values() for n in pins.values()}
        wire_nets = {t.GetNetname() for t in board.GetTracks()}
        pinless = {n for n in wire_nets if n not in pinned and n}
        print(f"  nets with no header pin (never ripped): "
              f"{len(pinless)} -> {sorted(pinless)[:12]}")
        if a.spur:
            # --spur: rip only what hangs off J1. The region predicate above
            # takes whole gutters, including other nets' distribution copper
            # that merely runs through them -- see rip_spur().
            ripped, roots, nstops = rip_spur(board, keep_nets=pinless)
            census(ripped, "ripped (J1 spur only)")
            print(f"  {roots} spur root(s) on J1, {nstops} stopping pad(s)")
        else:
            ripped, spared = rip(board, anchors, pinless)
            census(ripped, "ripped")
            print(f"  spared by the pad-anchor rule: {spared} segment(s)")

    print("\nsurviving copper per net (the rip must NOT have eaten the trunks):")
    for net in ("ROW0", "ROW3", "ROW5", "ROW20", "GND", "+3V3", "CSEL4"):
        n, y0, y1, x0, x1 = net_copper(board, net)
        if n and y0 is not None:
            print(f"  {net:<7} {n:4d} seg  y {y0:7.2f}..{y1:7.2f}  "
                  f"x {x0:7.2f}..{x1:7.2f}")

    if a.del_j1:
        # J1 itself has to go, not just its spurs. The route test otherwise
        # "succeeds" by ending on a J1 pad -- four +3V3 pins do exactly that --
        # which is a connection to a part that will not be there.
        for fp in list(board.GetFootprints()):
            if fp.GetReference() == "J1":
                board.Remove(fp)
                GRAVE.append(fp)
                print(f"\ndeleted J1 ({fp.GetFPID().GetLibItemName()})")

    if a.save:
        # Whether the rip orphaned anything is a question about the *board*, so
        # it has to be asked with a real connectivity engine, not a raster. The
        # raster version of this check reported GND as 28 fragments on the
        # pristine board -- a board DRC calls fully connected -- so it was
        # answering a different question. Save and let kicad-cli decide:
        # `unconnected_items` is the authoritative count.
        pcbnew.SaveBoard(a.save, board)
        print(f"\nsaved to {a.save} -- run DRC on it for the real count")
        return

    # --- the clearance model, exactly as the router would build it ----------
    keep = 0.2 + TRACK_W / 2 + a.safety
    print(f"\ngrid: step {a.step}, keep {keep:.2f} (track), "
          f"{0.2 + VIA_DIA/2 + a.safety:.2f} (via), "
          f"edge {edge_clear + TRACK_W/2 + a.safety:.2f}")
    grid = NGrid(board, a.step, keep,
                 edge_clear + TRACK_W / 2 + a.safety,
                 0.2 + VIA_DIA / 2 + a.safety,
                 edge_clear + VIA_DIA / 2 + a.safety, layers)
    # The header pads being flooded from must NOT be obstacles. A pad is in
    # the grid as a box, so its own cells read D=0 -- illegal -- and BFS then
    # cannot hop the keep ring around it and reports "reach = seed count",
    # which looks exactly like a seal. The router has the same rule for the
    # other reason: `obstacles(exclude)` drops the net it is routing.
    hdr_uuid = {p.m_Uuid.AsString()
                for ref in hdr for p in hdr[ref].Pads()}
    hdr_pads = [p for ref in hdr for p in hdr[ref].Pads()]
    items = list(board.GetTracks())
    for fp in board.GetFootprints():
        items += [p for p in fp.Pads()
                  if p.m_Uuid.AsString() not in hdr_uuid]
    grid.build(items)
    print(f"  grid {grid.nx} x {grid.ny}, x0 {grid.x0:.2f} y0 {grid.y0:.2f}, "
          f"legal cells: " + ", ".join(
              f"{board.GetLayerName(l)} {int(grid.OK[l].sum()):,}"
              for l in layers))
    names = []
    for it in items:
        try:
            names.append(it.GetNetname())
        except AttributeError:
            names.append("?")

    for ref in ("J1A", "J1B"):
        if ref not in hdr:
            continue
        print(f"\n{ref} @({hdr[ref].GetPosition().x/S:.2f},"
              f"{hdr[ref].GetPosition().y/S:.2f})")
        for pin in pins:
            pad = hdr[ref].FindPadByNumber(pin)
            if pad is None:
                print(f"    pin {pin}: no such pad")
                continue
            net = ASSIGN[ref].get(int(pin), "")
            pos = pad.GetPosition()
            # Per net, not the shared grid: see net_grid().
            g, gnames = net_grid(board, net, grid, layers)
            seeds = pad_cells(g, pad, layers)
            print(f"    pin {pin:<3} @({pos.x/S:7.2f},{pos.y/S:7.2f})  "
                  f"-> {net:<6} {len(seeds)} seed cell(s)")
            report(g, board, seeds, gnames)

    # --- did the rip break any net in two? ---------------------------------
    if a.frag:
        print("\ncopper connectivity after the rip "
              "(>1 component = the rip orphaned something):")
        comp = components(grid, names, board, layers)
        bad = 0
        for net in sorted(comp, key=lambda n: (-len(comp[n]), n)):
            c = comp[net]
            if len(c) < 2 and net not in (
                    "GND", "+3V3") and net not in a.frag.split(","):
                continue
            flag = "  <== FRAGMENTED" if len(c) > 1 else ""
            print(f"  {net:<7} {len(c):2d} component(s){flag}")
            for cnt, x0, y0, x1, y1 in c[:4]:
                print(f"        {cnt:8,} cells  x {x0:7.2f}..{x1:7.2f}  "
                      f"y {y0:7.2f}..{y1:7.2f}")
            bad += len(c) > 1
        print(f"  {bad} net(s) fragmented by the rip")

    # --- the real test: A* from each header pin to its net's own copper -----
    if not a.route and not a.emit:
        return
    want = [w.strip() for w in a.route.split(",")] if a.route else []
    for ref in ("J1A", "J1B"):
        if ref not in hdr:
            continue
        for pin, net in sorted(ASSIGN[ref].items()):
            if net not in want:
                continue
            # Per-net grid: the net's own copper is a goal, not an obstacle,
            # which is the router's own rule (obstacles(exclude)). Skipping it
            # is what makes a pad's cells legal and the search able to start.
            g2, _ = net_grid(board, net, grid, layers, hdr_uuid)
            src = hdr[ref].FindPadByNumber(pin)
            seeds = pad_cells(g2, src, layers)
            path, ln, err = route(g2, board, seeds, net, layers,
                                  exclude_pads=hdr_pads)
            if err == "no path":
                d = ln[0] * a.step if ln and ln[1] else float("inf")
                # Say whether the goal was even legal. A NO PATH whose goals
                # are all illegal is a statement about the grid, not the board
                # -- the search can only ever step onto an OK cell, so an
                # illegal goal is unreachable however empty the board is.
                # Quoting the two counts together is what keeps that honest.
                # The header pads are dropped, exactly as route() drops them,
                # or the count would include goals the search never got.
                boxes = [pad_box(p) for p in hdr_pads]

                def outside(i, j):
                    x, y = g2.x0 + i * a.step, g2.y0 + j * a.step
                    return not any(b[0] <= x <= b[2] and b[1] <= y <= b[3]
                                   for b in boxes)

                gl = {(l, i, j) for (l, i, j)
                      in cells_of(g2, own_items(board, net), layers) - set(seeds)
                      if outside(i, j)}
                lok = sum(1 for (l, i, j) in gl if g2.OK[l][j, i])
                print(f"  {ref}.{pin:<3} -> {net:<6} NO PATH  closest "
                      f"{d:6.2f}mm   goals {len(gl)} ({lok} legal)")
            elif err:
                print(f"  {ref}.{pin:<3} -> {net:<6} {err}")
            else:
                tgt = route_endpoint(g2, path)
                print(f"  {ref}.{pin:<3} -> {net:<6} PATH     {ln:7.2f}mm  "
                      f"({len(path)} cells) ends at "
                      f"({tgt[0]:7.2f},{tgt[1]:7.2f}) -> "
                      + nearest_own(board, tgt[0], tgt[1], net)[1])

    # --- lay the copper down, priority first, incrementally ------------------
    if not a.emit:
        return
    if a.emit == "auto":
        order = measure_order(board, hdr, hdr_pads, grid, layers, hdr_uuid,
                              a.step)
    else:
        order = pins_of(a.emit)
    emit_all(board, hdr, order, layers, a, keep)


def pins_of(spec):
    """Parse `--emit` into an ordered list of (ref, pin) to lay down.

    Three forms, and the order is the whole experiment:

    * `all` -- J1A then J1B, pin by pin;
    * `J1A.1:ROW3` -- one specific pin;
    * `ROW3` -- every pin carrying that net, which is what makes an ordering
      by *net* expressible without listing all forty pins.

    Whatever is named comes first, in the order named; every pin not named
    follows in pin order. Sequential routing is greedy, so an early route can
    spend a lane a later one needed, and this is how that gets steered.
    """
    if spec.strip() == "all":
        return [(ref, pin) for ref in ("J1A", "J1B")
                for pin in sorted(ASSIGN[ref])]
    first = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "." not in item:
            for ref in ("J1A", "J1B"):
                for pin in sorted(ASSIGN[ref]):
                    if ASSIGN[ref][pin] == item and (ref, pin) not in first:
                        first.append((ref, pin))
            continue
        where, _, _net = item.partition(":")
        ref, _, pin = where.partition(".")
        if (ref, int(pin)) not in first:
            first.append((ref, int(pin)))
    for ref in ("J1A", "J1B"):
        for pin in sorted(ASSIGN[ref]):
            if (ref, pin) not in first:
                first.append((ref, pin))
    return first


def measure_order(board, hdr, hdr_pads, proto, layers, hdr_uuid, step,
                  priority=("ROW3", "ROW5")):
    """Order the 40 pins by how far each has to travel, shortest first.

    Sequential routing is greedy, and the greedy failure is always the same
    shape: a net with a long detour available takes it, and the detour spends
    a lane that some short-hop net was going to need. Measured on this board,
    routing J1B pin by pin let ROW19 wander 92 tracks and left ROW20 four
    millimetres short of its own trunk.

    Path length is the proxy for slack. Every pin is measured on the board as
    it stands *before* any of this copper exists, so the number is a property
    of the design, not of the order being tested -- which is what makes the
    sort self-calibrating instead of a hand-tuned table. The shortest routes
    have the least freedom to go around something, so they go first.

    ROW3 and ROW5 are pinned to the front regardless: the standing instruction
    is to get them out of the 3x2mm box first and let the neighbours route
    around *them*.
    """
    lens = []
    for ref in ("J1A", "J1B"):
        if ref not in hdr:
            continue
        for pin in sorted(ASSIGN[ref]):
            net = ASSIGN[ref][pin]
            g2, _ = net_grid(board, net, proto, layers, hdr_uuid)
            src = hdr[ref].FindPadByNumber(pin)
            seeds = pad_cells(g2, src, layers)
            _, ln, err = route(g2, board, seeds, net, layers,
                               exclude_pads=hdr_pads)
            if err or ln is None:
                # No isolated path at all: the pin has no route to give up,
                # so order it before everything that might take its space.
                lens.append((-1.0, ref, pin, net))
                continue
            lens.append((ln, ref, pin, net))
    # Ascending length; ref and pin only break ties, so the order is
    # reproducible run to run.
    lens.sort(key=lambda t: (t[0], t[1], t[2]))
    head = [t for t in lens if t[3] in priority]
    head.sort(key=lambda t: list(priority).index(t[3]))
    rest = [t for t in lens if t[3] not in priority]
    order = [(r, p) for _, r, p, _ in head + rest]
    print("\norder (measured isolated path length, shortest first):")
    for ln, r, p, net in head + rest:
        print(f"  {r}.{p:<3} {net:<6} {ln:7.2f}mm" if ln >= 0
              else f"  {r}.{p:<3} {net:<6}   unreachable in isolation")
    return order


def emit_all(board, hdr, order, layers, a, keep):
    """Route each header pin to its net's own copper and emit real tracks.

    The order is the whole point, and so is the rebuild. Every pin gets a
    grid built from the board *as it stands at that moment*, so the copper
    the previous pin just emitted is an obstacle to this one -- which is what
    makes the sequence a routing, and not forty independent routes that
    happen to overlap.

    `Router.route` already does exactly this; it is handed the header pads as
    things to steer away from and to refuse as goals, and it re-reads the
    board for each pad. What is added here is the ordering.
    """
    r = Router(board, a.step, a.safety, 0.2, layers,
               board.GetDesignSettings().m_CopperEdgeClearance / S,
               soft=(a.soft_radius, a.soft_weight) if a.soft_radius else None,
               ref="J1A", extra_refs=("J1B",))
    print(f"\nemit: keep {r.keep:.3f}, via {r.pad_keep:.3f}, "
          f"edge {r.edge_keep:.3f}, soft "
          + (f"r={a.soft_radius} w={a.soft_weight}" if a.soft_radius else "off"))
    total_t = total_v = 0
    for ref, pin in order:
        net = ASSIGN[ref][pin]
        # Every pin of a shared net is routed, never skipped: GND has two pins
        # on J1A and three on J1B, and each one has to reach the plane on its
        # own. The later ones are cheap because the earlier copper is already
        # a goal, which is the honest reason they are cheap -- not a reason to
        # treat them as done.
        r.j1 = hdr[ref]
        recs = r.route(net, lock=False)
        nt = sum(x[3] for x in recs)
        nv = sum(x[4] for x in recs)
        total_t += nt
        total_v += nv
        print(f"  {ref}.{pin:<3} {net:<6} {nt:3d} track(s) {nv:2d} via(s)")
    print(f"  total {total_t} track(s), {total_v} via(s) for "
          f"{len(order)} pin(s)")
    if a.out:
        pcbnew.SaveBoard(a.out, board)
        print(f"\nsaved to {a.out}")


if __name__ == "__main__":
    main()
