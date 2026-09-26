"""Minimal rip-up for an unrouted J1 net, by greedy wall removal.

The bisection of rectangular drop boxes showed a linear grind -- each 3mm of
rip-up buys about 3mm of northward creep -- which is the signature of a
corridor saturated by the nets already in it, not of one bad bottleneck. A
rectangle is the wrong primitive for that: it lifts items whether or not they
are in the way, and the answer to "what must move" comes out as a box rather
than a list of nets.

This asks the question directly. Flood from the pad; if the flood does not
reach the net's own copper, look at the wall cells bordering the flooded
region, rank the items owning them, drop the worst, and repeat. Every step is
one flood. The output is the ordered list of items to lift, and the step at
which the net first gets out is the minimum rip-up for that ordering.

Rebuilding the grid after each drop would dominate the runtime (a full stamp
of 3700 items per iteration), so the scatter is built once and kept as a
sorted (cell, item, distance) index. Dropping an item is then a mask, and the
per-cell minimum is a segmented ``minimum.reduceat``.

    python greedy.py <board> --nets ROW3 [--max-drop 80]
"""
import argparse

import numpy as np
import pcbnew

from flood import NB8, shift, spread
from probe import item_shape, on_layer

S = 1e6
INF = np.float32(1e9)


class ItemIndex:
    """(cell, item, distance) scatter for every other-net item, per layer."""

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
        self.ncells = self.nx * self.ny
        self.stamp = max(keep, edge_keep, pad_keep) + 0.5

        xs = self.x0 + np.arange(self.nx) * step
        ys = self.y0 + np.arange(self.ny) * step
        self.X, self.Y = np.meshgrid(xs, ys)
        self.EG = np.minimum.reduce([self.X - self.bb[0], self.bb[2] - self.X,
                                     self.Y - self.bb[1], self.bb[3] - self.Y])

    def ij(self, x, y):
        return (int(round((x - self.x0) / self.step)),
                int(round((y - self.y0) / self.step)))

    def xy(self, i, j):
        return self.x0 + i * self.step, self.y0 + j * self.step

    def build(self, items):
        self.items = items
        stamp = self.stamp
        self.idx = {}
        for lay in self.layers:
            ci, ii, dd = [], [], []
            for no, it in enumerate(items):
                shape = item_shape(it)
                if shape is None or not on_layer(it, lay):
                    continue
                ax, ay, bx, by, r, box = shape
                reach = stamp if box else r + stamp
                i0 = max(0, int((ax - reach - self.x0) / self.step))
                i1 = min(self.nx - 1,
                         int((bx + reach - self.x0) / self.step) + 1)
                j0 = max(0, int((ay - reach - self.y0) / self.step))
                j1 = min(self.ny - 1,
                         int((by + reach - self.y0) / self.step) + 1)
                if i1 < i0 or j1 < j0:
                    continue
                px = self.X[j0:j1 + 1, i0:i1 + 1]
                py = self.Y[j0:j1 + 1, i0:i1 + 1]
                if box:
                    dx = np.maximum(np.maximum(ax - px, 0.0), px - bx)
                    dy = np.maximum(np.maximum(ay - py, 0.0), py - by)
                    d = np.sqrt(dx * dx + dy * dy).astype(np.float32)
                else:
                    d = (self._seg_dist(px, py, ax, ay, bx, by)
                         - np.float32(r)).astype(np.float32)
                cells = ((np.arange(j0, j1 + 1)[:, None] * self.nx
                          + np.arange(i0, i1 + 1)[None, :]).ravel())
                ci.append(cells)
                ii.append(np.full(cells.size, no, np.int32))
                dd.append(d.ravel())
            ci = np.concatenate(ci)
            ii = np.concatenate(ii)
            dd = np.concatenate(dd)
            order = np.argsort(ci, kind="stable")
            order = order.astype(np.int64)
            CI, II, DD = ci[order], ii[order], dd[order]
            # segment boundaries: one per cell that has at least one entry
            starts = np.flatnonzero(np.r_[True, CI[1:] != CI[:-1]])
            seg_cell = CI[starts]
            seg_of_cell = np.full(self.ncells, -1, np.int32)
            seg_of_cell[seg_cell] = np.arange(starts.size)
            self.idx[lay] = (CI, II, DD, starts, seg_cell, seg_of_cell,
                             seg_of_cell[CI])

    @staticmethod
    def _seg_dist(px, py, ax, ay, bx, by):
        if ax == bx and ay == by:
            return np.sqrt((px - ax) ** 2 + (py - ay) ** 2).astype(np.float32)
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0.0, 1.0)
        return np.sqrt((px - (ax + t * dx)) ** 2
                       + (py - (ay + t * dy)) ** 2).astype(np.float32)

    def solve(self, alive, lay):
        """Per-cell (distance, owner) on one layer over the items still up."""
        CI, II, DD, starts, seg_cell, seg_of_cell, entry_seg = self.idx[lay]
        vals = np.where(alive[II], DD, INF)
        dmin = np.minimum.reduceat(vals, starts)
        D = np.full(self.ncells, INF, np.float32)
        D[seg_cell] = dmin
        hit = alive[II] & (DD <= dmin[entry_seg])
        MAXI = np.iinfo(np.int32).max
        own = np.minimum.reduceat(np.where(hit, II, MAXI), starts)
        own = np.where(own == MAXI, -1, own)   # every item here was dropped
        OWN = np.full(self.ncells, -1, np.int32)
        OWN[seg_cell] = own
        return (D.reshape(self.ny, self.nx).copy(),
                OWN.reshape(self.ny, self.nx).copy())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", nargs="*", required=True)
    ap.add_argument("--ref", default="J1")
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--clearance", type=float, default=0.2)
    ap.add_argument("--track-w", type=float, default=0.2,
                    help="track width to measure room for; 0.127 (5 mil) "
                         "drops the pitch from 0.4 to 0.327mm in the corridor")
    ap.add_argument("--via-dia", type=float, default=0.6)
    ap.add_argument("--safety", type=float, default=0.0)
    ap.add_argument("--max-drop", type=int, default=120)
    ap.add_argument("--max-iter", type=int, default=4000)
    #: Confine the rip-up to items whose *position* falls in this box. The
    #: flood's drop-box test proved that x[128,174] y[241,246] is sufficient
    #: (331 items) and that x[128,174] y[241,244] is not -- but a box drops
    #: everything it covers, so this asks the greedy for the subset that is
    #: actually load-bearing. Without a restriction the greedy wanders off to
    #: the right-edge highway and burns its whole budget 201 items in.
    ap.add_argument("--drop-box", nargs=4, type=float, default=None,
                    metavar=("X0", "Y0", "X1", "Y1"))
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    ds = board.GetDesignSettings()
    edge_clear = ds.m_CopperEdgeClearance / S
    keep = a.clearance + a.track_w / 2 + a.safety
    pad_keep = a.clearance + a.via_dia / 2 + a.safety
    edge_keep = edge_clear + a.track_w / 2 + a.safety
    via_edge_keep = edge_clear + a.via_dia / 2 + a.safety
    print(f"edge rule {edge_clear}mm | track {a.track_w:.3f}mm keep {keep:.3f} "
          f"| via {a.via_dia:.3f}mm keep {pad_keep:.3f} | safety {a.safety}")
    import sys
    sys.stdout.flush()
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    j1 = next(fp for fp in board.GetFootprints() if fp.GetReference() == a.ref)

    for name in a.nets:
        own = [t for t in board.GetTracks() if t.GetNetname() == name]
        for fp in board.GetFootprints():
            own += [p for p in fp.Pads() if p.GetNetname() == name]
        pad = next((p for p in j1.Pads() if p.GetNetname() == name), None)
        if pad is None:
            print(f"\n{name}: no {a.ref} pad")
            continue

        others = [t for t in board.GetTracks() if t.GetNetname() != name]
        for fp in board.GetFootprints():
            others += [p for p in fp.Pads() if p.GetNetname() != name]

        idx = ItemIndex(board, a.step, keep, edge_keep, pad_keep,
                        via_edge_keep, layers)
        idx.build(others)

        # goals: the net's own copper, minus the J1 pad
        goals = {l: np.zeros((idx.ny, idx.nx), bool) for l in layers}
        pu = pad.m_Uuid.AsString()
        for it in own:
            if isinstance(it, pcbnew.PAD) and it.m_Uuid.AsString() == pu:
                continue
            sh = item_shape(it)
            if sh is None:
                continue
            cx, cy = (sh[0] + sh[2]) / 2, (sh[1] + sh[3]) / 2
            for l in layers:
                if on_layer(it, l) and 0 <= idx.ij(cx, cy)[0] < idx.nx \
                        and 0 <= idx.ij(cx, cy)[1] < idx.ny:
                    goals[l][idx.ij(cx, cy)[1], idx.ij(cx, cy)[0]] = True

        pp = pad.GetPosition()
        si, sj = idx.ij(pp.x / S, pp.y / S)
        r = pad.GetBoundingBox()
        seed = np.zeros((idx.ny, idx.nx), bool)
        for di in range(-4, 5):
            for dj in range(-4, 5):
                i, j = si + di, sj + dj
                if not (0 <= i < idx.nx and 0 <= j < idx.ny):
                    continue
                x, y = idx.xy(i, j)
                if (r.GetLeft() / S <= x <= r.GetRight() / S
                        and r.GetTop() / S <= y <= r.GetBottom() / S):
                    seed[j, i] = True
        if not seed.any():
            seed[sj, si] = True

        # Pads are fixed: a pad that is in the way means a part must move, so
        # they are reported but never dropped.
        droppable = np.array([not isinstance(it, pcbnew.PAD) for it in others])
        if a.drop_box:
            bx0, by0, bx1, by1 = a.drop_box
            outside = 0
            for no, it in enumerate(others):
                if not droppable[no]:
                    continue
                p = it.GetPosition()
                if not (bx0 <= p.x / S <= bx1 and by0 <= p.y / S <= by1):
                    droppable[no] = False
                    outside += 1
            print(f"  rip-up confined to x[{bx0},{bx1}] y[{by0},{by1}]: "
                  f"{int(droppable.sum())} droppable of {len(others)} "
                  f"({outside} held fixed)")

        print(f"\n=== {name} === pad ({pp.x/S:.3f},{pp.y/S:.3f}) "
              f"{int(seed.sum())} seed cell(s), "
              f"{int(sum(g.sum() for g in goals.values()))} goal cell(s), "
              f"{len(others)} other-net item(s)")

        alive = np.ones(len(others), bool)
        picked = []
        for step in range(a.max_drop + 1):
            OK, OWN = {}, {}
            VOK = np.ones((idx.ny, idx.nx), bool)
            for lay in layers:
                D, OWN[lay] = idx.solve(alive, lay)
                OK[lay] = (D >= np.float32(keep)) & (idx.EG >= edge_keep)
                VOK &= D >= np.float32(pad_keep)
            VOK &= idx.EG >= via_edge_keep

            reach = {l: np.zeros((idx.ny, idx.nx), bool) for l in layers}
            reach[pcbnew.F_Cu] = seed.copy()
            for _ in range(a.max_iter):
                before = sum(int(x.sum()) for x in reach.values())
                for lay in layers:
                    rr = reach[lay]
                    for di, dj in NB8:
                        rr = spread(rr, OK[lay], di, dj)
                    reach[lay] = rr
                for k, lay in enumerate(layers):
                    reach[layers[1 - k]] |= reach[lay] & VOK
                if sum(int(x.sum()) for x in reach.values()) == before:
                    break

            hit = sum(int((reach[l] & goals[l]).sum()) for l in layers)
            cells = sum(int(x.sum()) for x in reach.values())
            if hit:
                print(f"  step {step}: OUT -- {hit} goal cell(s) reached, "
                      f"{cells} cell(s), {len(picked)} item(s) lifted")
                break

            # rank the walls bordering the reached region
            tally = {}
            for lay in layers:
                illegal = ~OK[lay]
                for di, dj in NB8:
                    near = shift(reach[lay], di, dj) & illegal
                    if not near.any():
                        continue
                    js, iss = np.nonzero(near)
                    for o in OWN[lay][js, iss]:
                        if o >= 0:
                            tally[int(o)] = tally.get(int(o), 0) + 1
            cand = [(c, o) for o, c in tally.items() if alive[o] and droppable[o]]
            if not cand:
                print(f"  step {step}: STUCK -- no droppable wall "
                      f"({cells} cell(s)); pads own every wall")
                break
            cand.sort(reverse=True)
            top = cand[:6]
            desc = "  ".join(
                f"{others[o].GetNetname()}"
                f"{'/' + ('via' if isinstance(others[o], pcbnew.PCB_VIA) else 'trk')}"
                f":{c}" for c, o in top)
            print(f"  step {step:3d}: {cells:6d} cell(s)  "
                  f"walls {desc}")
            best = cand[0][1]
            alive[best] = False
            picked.append(best)

        if picked:
            print(f"\n  rip-up list ({len(picked)} item(s)):")
            for k, o in enumerate(picked):
                it = others[o]
                p = it.GetPosition()
                kind = ("via" if isinstance(it, pcbnew.PCB_VIA) else "trk")
                extra = ""
                if kind == "trk":
                    s, e = it.GetStart(), it.GetEnd()
                    extra = (f" ({s.x/S:.2f},{s.y/S:.2f})->"
                             f"({e.x/S:.2f},{e.y/S:.2f})")
                print(f"    {k+1:3d}. {kind:<3} {it.GetNetname():<8} "
                      f"@({p.x/S:.2f},{p.y/S:.2f}){extra}")


if __name__ == "__main__":
    main()
