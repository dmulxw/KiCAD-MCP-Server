"""Re-plan the J1 fan-out: route the priority nets first, then let the
neighbours route around them.

The corridor south of J1 is saturated at exactly the design-rule floor, so no
local tweak gets ROW3/ROW5 out. Measured on this board:

* 5 mil (0.127mm) narrowing buys ~2 grid cells and opens no via site -- the
  channel is bounded by *neighbouring tracks*, not by the track's own width;
* a 0.4/0.2mm micro-via cannot fit between 0.5mm-pitch pads (it needs 0.8mm
  of gap, there is 0.70mm);
* with every other-net item lifted in x[128,174] y[241,246] (331 items, 32
  nets) both nets reach their trunks -- so the corridor has room, it is just
  holding the wrong nets;
* grafting the old routing in short-circuits ROW3 into 28 other nets and
  ROW5 into 30.

So the fix is the one the design review asked for. This does it in one pass:

1. lift every track/via in the corridor, remembering their exact geometry;
2. route the priority nets (ROW3/ROW5) into the space that frees;
3. put the lifted items back -- all except the ones the new copper now
   collides with;
4. re-route just the nets that had to give way.

Step 3 is what keeps this cheap. Re-routing all 32 ripped nets blind would
mean 32 searches; in practice the new ROW3/ROW5 copper displaces only a
handful, and everything else goes back exactly where it was -- which is
guaranteed legal, since the original board was.

Grid resolution is not free. A run between two sampled cells can bow up to
0.707*step from them, so sampling only proves the rule if safety >= 0.707*step;
at step 0.05 that is 0.036mm. The J1 escape caps safety at 0.05 (pad 4's
neighbour is 0.35mm away and keep = clearance + w/2 + safety must stay under
it), so 0.04 is the setting that satisfies both.

    python replan.py <src.kicad_pcb> --out <dst.kicad_pcb> --first ROW3 ROW5
"""
import argparse
import os
import time

import numpy as np
import pcbnew

from probe import Ghost, NGrid, astar, item_shape, item_seg, on_layer

S = 1e6
TRACK_W = 0.2
VIA_DIA = 0.6
VIA_DRILL = 0.3


class Geom:
    """A lifted item's geometry, as plain numbers -- no SWIG handles.

    Recording tuples rather than cloning the BOARD_ITEM keeps the restore
    path independent of the item classes, and makes it explicit which
    fields have to be reproduced for a track or via to come back identical.
    """

    def __init__(self, it):
        self.net = it.GetNetname()
        self.locked = it.IsLocked()
        self.via = isinstance(it, pcbnew.PCB_VIA)
        p = it.GetPosition()
        self.px, self.py = p.x / S, p.y / S
        if self.via:
            # PCB_VIA::GetWidth() asserts unless handed a layer in this build,
            # so take the pad size off the bounding box (a via's is square).
            self.w = it.GetBoundingBox().GetWidth()
            self.drill = it.GetDrill()
        else:
            s, e = it.GetStart(), it.GetEnd()
            self.x0, self.y0 = s.x / S, s.y / S
            self.x1, self.y1 = e.x / S, e.y / S
            self.w = it.GetWidth()
            self.layer = it.GetLayer()

    def bbox(self):
        if self.via:
            r = self.w / S / 2
            return self.px - r, self.py - r, self.px + r, self.py + r
        r = self.w / S / 2
        return (min(self.x0, self.x1) - r, min(self.y0, self.y1) - r,
                max(self.x0, self.x1) + r, max(self.y0, self.y1) + r)

    def ghost(self, layers):
        """This item as an obstacle-only shape for NGrid."""
        if self.via:
            r = self.w / S / 2
            return Ghost((self.px - r, self.py - r, self.px + r, self.py + r,
                          0.0, True), layers)
        r = self.w / S / 2
        return Ghost((min(self.x0, self.x1), min(self.y0, self.y1),
                      max(self.x0, self.x1), max(self.y0, self.y1), r, False),
                     [self.layer])

    def samples(self, req):
        """Points to test against the new copper, and the layer they are on."""
        if self.via:
            return [(self.px, self.py, pcbnew.F_Cu), (self.px, self.py,
                                                      pcbnew.B_Cu)]
        L = ((self.x1 - self.x0) ** 2 + (self.y1 - self.y0) ** 2) ** 0.5
        n = max(2, int(L / req) + 1)
        return [(self.x0 + k / n * (self.x1 - self.x0),
                 self.y0 + k / n * (self.y1 - self.y0), self.layer)
                for k in range(n + 1)]

    def restore(self, board, net):
        if self.via:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(int(round(self.px * S)),
                                          int(round(self.py * S))))
            v.SetWidth(int(self.w))
            v.SetDrill(int(self.drill))
            v.SetNet(net)
            v.SetLocked(self.locked)
            board.Add(v)
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(round(self.x0 * S)),
                                       int(round(self.y0 * S))))
            t.SetEnd(pcbnew.VECTOR2I(int(round(self.x1 * S)),
                                     int(round(self.y1 * S))))
            t.SetWidth(int(self.w))
            t.SetLayer(self.layer)
            t.SetNet(net)
            t.SetLocked(self.locked)
            board.Add(t)


def cells_of(grid, items, layers):
    """Every grid cell covered by `items`' copper, as an A* goal set.

    Sampling the whole shape rather than its centre matters: a ROW trunk is
    60mm long, and marking only its midpoint would send the search to the
    middle of the board instead of stopping at the first copper it touches.
    """
    goals = set()
    for it in items:
        sh = item_shape(it)
        if sh is None:
            continue
        ax, ay, bx, by, r, box = sh
        # For a track, walk the centreline, not the bbox diagonal -- see
        # probe.item_seg().  On a diagonal the two differ, and the bbox
        # diagonal seeds goal cells the net does not own.
        seg = item_seg(it)
        if seg is not None:
            ax, ay, bx, by = seg
        lay_here = [l for l in layers if on_layer(it, l)]
        if not lay_here:
            continue
        L = max(abs(bx - ax), abs(by - ay))
        n = max(2, int(L / grid.step) + 1)
        for k in range(n + 1):
            u = k / n
            i, j = grid.ij(ax + u * (bx - ax), ay + u * (by - ay))
            if 0 <= i < grid.nx and 0 <= j < grid.ny:
                for l in lay_here:
                    goals.add((l, i, j))
    return goals


def pad_cells(grid, pad, layers):
    """Sample the pad as the *copper*, not as its bounding box.

    The 9x9 lattice runs over the bbox, and for a round pad the four corners
    sit outside the metal -- 0.35mm outside for the 1.7mm PTH header pins.
    Those corners are perfectly legal cells (they clear both this pad and its
    neighbours by more than `keep`), so A* is happy to start from one, `emit`
    writes the first segment from there, and the track ends up floating
    beside the pad it was meant to attach to. The board then reads as fully
    routed while every single pin is `unconnected_items`.

    `HitTest` is the pad's own shape test, so this keeps the samples that lie
    in copper for round, rect, oval and roundrect alike. If a pad is so small
    that no lattice point lands inside it, fall back to the centre, which is
    always in copper.
    """
    bb = pad.GetBoundingBox()
    x0, y0 = bb.GetLeft() / S, bb.GetTop() / S
    x1, y1 = bb.GetRight() / S, bb.GetBottom() / S
    lay_here = [l for l in layers if on_layer(pad, l)] or [pcbnew.F_Cu]
    hits = []
    for k in range(9):
        for m in range(9):
            x, y = x0 + (x1 - x0) * k / 8, y0 + (y1 - y0) * m / 8
            if pad.HitTest(pcbnew.VECTOR2I(int(round(x * S)),
                                           int(round(y * S)))):
                hits.append((x, y))
    if not hits:
        c = pad.GetPosition()
        hits = [(c.x / S, c.y / S)]
    out = []
    for lay in lay_here:
        for x, y in hits:
            i, j = grid.ij(x, y)
            if 0 <= i < grid.nx and 0 <= j < grid.ny:
                out.append((lay, i, j))
    return list(dict.fromkeys(out))


def layer_runs(path):
    runs = [[path[0]]]
    for c in path[1:]:
        if c[0] != runs[-1][-1][0]:
            runs.append([c])
        else:
            runs[-1].append(c)
    return runs


def merge_run(run):
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


def emit(board, name, grid, path, lock=False):
    runs = layer_runs(path)
    tracks = []
    for run in runs:
        tracks.extend(merge_run(run))
    vias = []
    for k in range(1, len(runs)):
        c = runs[k][0]
        x, y = grid.xy(c[1], c[2])
        if any((x - vx) ** 2 + (y - vy) ** 2 < VIA_DIA ** 2 for vx, vy in vias):
            continue
        vias.append((x, y))

    net = board.FindNet(name)
    for x, y in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(round(x * S)), int(round(y * S))))
        v.SetWidth(int(VIA_DIA * S))
        v.SetDrill(int(VIA_DRILL * S))
        v.SetNet(net)
        v.SetLocked(lock)
        board.Add(v)
    n_t = 0
    for layer, i0, j0, i1, j1 in tracks:
        if i0 == i1 and j0 == j1:
            continue
        x0, y0 = grid.xy(i0, j0)
        x1, y1 = grid.xy(i1, j1)
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(round(x0 * S)), int(round(y0 * S))))
        t.SetEnd(pcbnew.VECTOR2I(int(round(x1 * S)), int(round(y1 * S))))
        t.SetWidth(int(TRACK_W * S))
        t.SetLayer(layer)
        t.SetNet(net)
        t.SetLocked(lock)
        board.Add(t)
        n_t += 1
    return n_t, len(vias)


class Router:
    def __init__(self, board, step, safety, clearance, layers, edge_clear,
                 soft=None, ghosts=None, ghost_weight=8.0, ref="J1",
                 extra_refs=()):
        self.board = board
        #: The connector supplying the pins to fan out, and any sibling that
        #: shares its nets. A sibling matters because its pads are *also* this
        #: net: leaving them in the goal set makes a GND pin route 80mm across
        #: the board to the other header's GND pin instead of to the plane
        #: those pins exist to join.
        self.ref = ref
        self.extra_refs = tuple(extra_refs)
        #: Lifted items, still invisible to the board but visible to the
        #: search. See Ghost: without these the priority route is chosen in a
        #: corridor that has been emptied and cannot tell a free lane from a
        #: trunk it is about to bisect.
        self.ghosts = ghosts or []
        self.step = step
        self.safety = safety
        self.clearance = clearance
        self.layers = layers
        self.edge_clear = edge_clear
        #: (radius, weight) for the crowding penalty, or None to minimise
        #: length alone. Length alone is the wrong objective on a saturated
        #: board: the shortest escape runs along the one free lane, which on
        #: this board is the J1 fan-out itself, and 25 nets lose their path to
        #: it. Charging for proximity makes the route pay for the space it
        #: takes and prefer the empty lanes instead.
        self.soft = soft
        #: Cost per grid step to spend inside the keep band of a ghost.
        self.ghost_weight = ghost_weight
        self.keep = clearance + TRACK_W / 2 + safety
        self.pad_keep = clearance + VIA_DIA / 2 + safety
        self.edge_keep = self.edge_clear + TRACK_W / 2 + safety
        self.via_edge_keep = self.edge_clear + VIA_DIA / 2 + safety
        wanted = {self.ref} | set(self.extra_refs)
        heads = [fp for fp in board.GetFootprints()
                 if fp.GetReference() in wanted]
        if not heads:
            raise SystemExit(f"no footprint named {sorted(wanted)} on board")
        self.j1 = next(fp for fp in heads if fp.GetReference() == self.ref)
        #: Every pin of every header, as UUIDs: none of these is ever a goal.
        self.head_pads = {p.m_Uuid.AsString()
                          for fp in heads for p in fp.Pads()}

    def obstacles(self, exclude):
        out = [t for t in self.board.GetTracks() if t.GetNetname() != exclude]
        for fp in self.board.GetFootprints():
            out += [p for p in fp.Pads() if p.GetNetname() != exclude]
        return out

    def ghosts_of(self, exclude):
        """The lifted items the search must route *through*, not over.

        An item belonging to the net being routed is not an obstacle -- it is
        the goal -- so it is left out here exactly as it is in `obstacles`.
        """
        return [gh for net, gh in self.ghosts if net != exclude]

    def route(self, name, ref="J1", lock=False, limit=None, goal_max_y=None):
        """Connect every J1 pad of `name` to the rest of its copper.

        A pad that is already connected yields a near-zero path and emits
        nothing, so running this over all of a net's J1 pads (GND has five,
        +3V3 four) needs no separate connectivity test.

        `limit` forbids travel outside a box. Left free, A* takes the shortest
        path it can find, which on a saturated board is a long detour that
        eats space other nets needed -- capping the search is how a compact
        escape gets found, and the smallest box that still admits a path is
        the most compact one.
        """
        pads = [p for p in self.j1.Pads() if p.GetNetname() == name]
        if not pads:
            print(f"  {name}: no {ref} pad")
            return 0, 0
        nt = nv = 0
        recs = []
        for src in pads:
            own = [t for t in self.board.GetTracks()
                   if t.GetNetname() == name]
            # The header pads are what we are connecting *to*; if any of them
            # counts as a goal, A* stops on the cell next door and returns a
            # two-cell path that connects nothing.
            for fp in self.board.GetFootprints():
                own += [p for p in fp.Pads()
                        if p.GetNetname() == name
                        and p.m_Uuid.AsString() not in self.head_pads]
            if goal_max_y is not None:
                # Reaching *any* of a net's 50-odd pads is not the same as
                # reaching its trunk: a route that stops at a stray pad still
                # leaves the net split. For a feasibility test, only the
                # northern copper counts.
                own = [it for it in own
                       if it.GetPosition().y / S <= goal_max_y]
            grid = NGrid(self.board, self.step, self.keep, self.edge_keep,
                         self.pad_keep, self.via_edge_keep, self.layers)
            # Real copper only. Ghosts are priced below, never walls here:
            # see the note there for why walling them off walls off the
            # escape as well.
            grid.build(self.obstacles(name))
            if limit:
                lx0, ly0, lx1, ly1 = limit
                ii, jj = np.meshgrid(np.arange(grid.nx), np.arange(grid.ny))
                xs = grid.x0 + ii * grid.step
                ys = grid.y0 + jj * grid.step
                inside = ((xs >= lx0) & (xs <= lx1)
                          & (ys >= ly0) & (ys <= ly1))
                for lay in self.layers:
                    grid.OK[lay] &= inside
                    grid.VOK &= inside
            soft = None
            if self.soft:
                radius, weight = self.soft
                span = max(radius - self.keep, 1e-6)
                soft = {}
                for lay in self.layers:
                    # 1.0 at the keep boundary, 0 beyond `radius`, so the
                    # search pays to hug copper and walks down the open lanes.
                    t = (radius - grid.D[lay]) / span
                    soft[lay] = (weight
                                 * np.clip(t, 0.0, 1.0)).astype(np.float32)
                    soft[lay][~grid.OK[lay]] = 0.0
            if self.ghosts:
                # Price the lifted copper rather than wall it off. Walling it
                # off walls off the escape: the corridor was lifted precisely
                # because the fan-out lanes had to open, and a hard ghost puts
                # them straight back. But ignoring it is what cut the trunks.
                #
                # A cost per cell inside the keep band does neither. Crossing a
                # 0.2mm trunk costs the ~14 cells of its band, so a long F.Cu
                # run that crosses 17 of them pays ~17*14*w, while dropping to
                # B.Cu pays one via pair -- fixed, small. On this board that is
                # the whole decision: x=127.95 crosses 17 trunks on F.Cu and
                # none on B.Cu, so the run belongs on B.Cu.
                gg = NGrid(self.board, self.step, self.keep, self.edge_keep,
                           self.pad_keep, self.via_edge_keep, self.layers)
                gg.build(self.obstacles(name) + self.ghosts_of(name))
                if soft is None:
                    soft = {lay: np.zeros((grid.ny, grid.nx), np.float32)
                            for lay in self.layers}
                for lay in self.layers:
                    t = (self.keep - gg.D[lay]) / self.keep
                    soft[lay] = soft[lay] + (self.ghost_weight
                                             * np.clip(t, 0.0, 1.0)
                                             ).astype(np.float32)
            start = pad_cells(grid, src, self.layers)
            goals = cells_of(grid, own, self.layers) - set(start)
            if not goals:
                # Say it rather than skipping. A net whose only copper is the
                # header's own pins has nothing to connect to, and silence
                # here reads as "already connected" when it is the opposite:
                # the design has no load on this net at all.
                p = src.GetPosition()
                print(f"  {name}: ({p.x/S:.3f},{p.y/S:.3f}) nothing outside "
                      f"the header pins to connect to -- net carries no load")
                continue
            path, _cross, expanded, closest = astar(
                grid, start, goals, 25.0, conflict=False, soft=soft)
            if path is None:
                d, at = closest
                where = ""
                if at:
                    x, y = grid.xy(at[1], at[2])
                    where = (f" closest {d * self.step:.2f}mm at "
                             f"({x:.2f},{y:.2f})")
                p = src.GetPosition()
                print(f"  {name}: NO PATH from ({p.x/S:.3f},{p.y/S:.3f})"
                      f"{where}")
                continue
            # Belt and braces on top of pad_cells: whatever cell A* chose to
            # start from, the emitted copper must begin *in* the pad. The pad
            # centre always qualifies, and the segment from it to the old
            # first cell stays well inside this pad's own copper -- the
            # nearest neighbouring pin is 2.54mm away with a 0.85mm radius, so
            # nothing else is within 1.69mm of the centre.
            c = src.GetPosition()
            ci, cj = grid.ij(c.x / S, c.y / S)
            if (path[0][1], path[0][2]) != (ci, cj):
                path = [(path[0][0], ci, cj)] + path
            ln = sum(((path[k][1] - path[k - 1][1]) ** 2
                      + (path[k][2] - path[k - 1][2]) ** 2) ** 0.5
                     for k in range(1, len(path))) * self.step
            a, b = emit(self.board, name, grid, path, lock=lock)
            nt += a
            nv += b
            p = src.GetPosition()
            recs.append((p.x / S, p.y / S, ln, a, b))
            print(f"  {name}: ({p.x/S:.3f},{p.y/S:.3f}) -> {ln:5.1f}mm, "
                  f"{a} track(s) {b} via(s)")
        return recs

    def clash_grid(self, nets):
        """Free space measured against `nets` only -- the new copper."""
        items = [t for t in self.board.GetTracks() if t.GetNetname() in nets]
        grid = NGrid(self.board, 0.05, self.clearance + TRACK_W / 2,
                     self.edge_clear + TRACK_W / 2,
                     self.clearance + TRACK_W / 2,
                     self.edge_clear + TRACK_W / 2, self.layers)
        grid.build(items)
        return grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", default=None)
    ap.add_argument("--first", nargs="+", default=["ROW3", "ROW5"],
                    help="nets to route before anything is put back")
    ap.add_argument("--box", nargs=4, type=float, required=True,
                    metavar=("X0", "Y0", "X1", "Y1"),
                    help="corridor to lift")
    ap.add_argument("--limit", nargs=4, type=float, default=None,
                    metavar=("X0", "Y0", "X1", "Y1"),
                    help="box the priority nets may not leave")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--safety", type=float, default=0.04)
    ap.add_argument("--clearance", type=float, default=0.2)
    ap.add_argument("--lock", action="store_true",
                    help="lock the new copper (Freerouting honours this)")
    ap.add_argument("--ghosts", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="make the lifted copper visible to the priority "
                         "route as obstacle-only geometry (default: on)")
    ap.add_argument("--ghost-weight", type=float, default=8.0,
                    help="cost per grid step inside a ghost's keep band")
    ap.add_argument("--soft", nargs=2, type=float, default=None,
                    metavar=("RADIUS", "WEIGHT"),
                    help="charge the priority nets for crowding: an extra "
                         "cost of up to WEIGHT per cell within RADIUS of "
                         "another net's copper")
    a = ap.parse_args()
    out = a.out or a.src

    t0 = time.time()
    board = pcbnew.LoadBoard(a.src)
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    x0, y0, x1, y1 = a.box
    edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S

    # 1. lift the corridor, keeping exact geometry.
    #
    # `graveyard` is load-bearing: BOARD::Remove hands the item to Python, and
    # once a removed proxy is collected SWIG loses the type registry for the
    # whole process -- after ~10 removals GetFootprints() starts returning bare
    # SwigPyObjects, and even a fresh LoadBoard fails. Holding every removed
    # item for the run keeps the registry intact.
    lifted, graveyard = [], []
    for t in list(board.GetTracks()):
        g = Geom(t)
        bx0, by0, bx1, by1 = g.bbox()
        if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            continue
        lifted.append(g)
        board.Remove(t)
        graveyard.append(t)
    print(f"lifted {len(lifted)} item(s) in x[{x0},{x1}] y[{y0},{y1}] "
          f"({len({g.net for g in lifted})} nets)  [{time.time()-t0:.0f}s]")

    # 2. route the priority nets into the space that freed
    #
    # The lifted copper goes back into the search as ghost obstacles. Leaving
    # it out is not neutral: the row trunks are horizontal on F.Cu and the
    # escape is vertical, so a blind search runs straight down the middle of
    # the panel on F.Cu and bisects every trunk it passes -- measured at
    # 0.15mm on this board, against a 0.2mm rule -- which is a whole-net
    # re-route for each of the 35 nets it crosses. Seeing the trunks turns
    # each crossing into a via pair, and the run then goes down the middle on
    # B.Cu where there is nothing to cut.
    ghosts = [(g.net, g.ghost(layers)) for g in lifted] if a.ghosts else []
    r = Router(board, a.step, a.safety, a.clearance, layers, edge_clear,
               soft=tuple(a.soft) if a.soft else None, ghosts=ghosts,
               ghost_weight=a.ghost_weight)
    print(f"step {a.step} safety {a.safety:.3f} -> track keep {r.keep:.3f}, "
          f"via keep {r.pad_keep:.3f}, edge keep {r.edge_keep:.3f}, "
          f"{len(ghosts)} ghost(s)")
    print("\n--- priority ---")
    for name in a.first:
        s = time.time()
        recs = r.route(name, lock=a.lock, limit=a.limit)
        n_t = sum(x[3] for x in recs)
        n_v = sum(x[4] for x in recs)
        print(f"    ({n_t} track(s), {n_v} via(s), {time.time()-s:.0f}s)")

    # 3. put the lifted items back, net by net.
    #
    # The unit is the net, not the item. Restoring item-by-item leaves a net
    # half-back -- a stub ending in mid-air where its neighbour was held -- and
    # the re-route below then starts on top of that half-routing, finds copper
    # in the very next cell, and emits a 0.1mm no-op while the rest of the net
    # stays cut. So: if any item of a net clashes with the new copper, none of
    # that net goes back and the whole net gets a fresh fan-out instead.
    #
    # A priority net is never judged against its own new copper. The rip
    # usually swallows the far end of the net it is being routed to -- ROW3's
    # bus starts inside the box -- and there the new track and the old bus
    # touch, which is the junction we just made, not a clash. Testing it as
    # one withholds exactly the copper the route was aiming at, and the net
    # then "re-routes" itself to a 0.1mm no-op.
    cg_for = {name: r.clash_grid(set(a.first) - {name}) for name in a.first}
    cg_any = r.clash_grid(set(a.first))

    def clashes(g):
        cg = cg_for.get(g.net, cg_any)
        req = a.clearance + g.w / S / 2
        for x, y, lay in g.samples(0.05):
            i, j = cg.ij(x, y)
            if not (0 <= i < cg.nx and 0 <= j < cg.ny):
                continue
            if float(cg.D[lay][j, i]) < req:
                return (x, y, lay, float(cg.D[lay][j, i]), req)
        return None

    if os.environ.get("REPLAN_WHY"):
        for g in lifted:
            hit = clashes(g)
            if hit:
                x, y, lay, d, req = hit
                print(f"    {g.net:<8} {'via' if g.via else 'trk'} "
                      f"({g.px if g.via else g.x0:.3f},"
                      f"{g.py if g.via else g.y0:.3f})->"
                      f"({g.px if g.via else g.x1:.3f},"
                      f"{g.py if g.via else g.y1:.3f}) "
                      f"{'F' if lay == pcbnew.F_Cu else 'B'} "
                      f"d={d:.3f} req={req:.3f} at ({x:.2f},{y:.2f})")

    broken = []                      # nets that must be re-routed, in lift order
    for g in lifted:
        if g.net not in broken and clashes(g):
            broken.append(g.net)
    broken_set = set(broken)
    back = [g for g in lifted if g.net not in broken_set]
    held = [g for g in lifted if g.net in broken_set]

    print(f"\n--- restore ---\n  {len(back)} item(s) back over "
          f"{len({g.net for g in back})} net(s); {len(held)} item(s) held, "
          f"whole-net re-route for {len(broken)} net(s)")
    for g in back:
        g.restore(board, board.FindNet(g.net))
    for name in broken:
        n = sum(1 for g in held if g.net == name)
        print(f"    re-route {name:<8} ({n} item(s) dropped)")

    # 4. re-route the nets that gave way. They are routed one at a time into
    #    the space the priority nets left, in the order they were lifted, so an
    #    earlier net's new copper is an obstacle for the later ones.
    print(f"\n--- re-route {len(broken)} net(s) ---")
    for name in broken:
        s = time.time()
        r.route(name, lock=a.lock)
        print(f"    ({time.time()-s:.0f}s)")

    board.BuildConnectivity()
    pcbnew.SaveBoard(out, board)
    print(f"\nsaved {out}  [{time.time()-t0:.0f}s total]")


if __name__ == "__main__":
    main()
