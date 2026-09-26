"""Flood the free space around an unrouted J1 net and name its pocket walls.

Answers two questions without an A*:

1. How far can this net legally reach at a given ``--safety``? (region size,
   per-layer extent, and whether it touches its own trunk at all)
2. What owns the copper sealing that region -- i.e. exactly which nets must be
   lifted for it to get out, ranked by how much wall they contribute.

A flood fill is O(cells) with no re-expansion, where the conflict-mode A* was
unbounded: its penalty made almost every revisit an "improvement", so the heap
grew without limit (15GB before it was killed).
"""
import argparse
from collections import defaultdict

import numpy as np
import pcbnew

from probe import NGrid, item_shape, on_layer

S = 1e6
NB8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def shift(a, di, dj, fill=False):
    """a[i,j] -> out[i,j] = a[i-di, j-dj] (out of range -> `fill`)."""
    out = np.full_like(a, fill)
    ny, nx = a.shape
    ys0, ys1 = max(0, -di), min(ny, ny - di)
    xs0, xs1 = max(0, -dj), min(nx, nx - dj)
    if ys0 >= ys1 or xs0 >= xs1:
        return out
    out[ys0:ys1, xs0:xs1] = a[ys0 - (-di):ys1 - (-di), xs0 - (-dj):xs1 - (-dj)]
    return out


def spread(r, OK, di, dj):
    src = shift(r, di, dj)
    if not src.any():
        return r
    if di and dj:
        ok = OK & shift(OK, di, 0) & shift(OK, 0, dj)
    else:
        ok = OK
    return r | (src & ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", nargs="*", required=True)
    ap.add_argument("--ref", default="J1")
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--clearance", type=float, default=0.2)
    #: Track width the flood is measuring room for. The board is packed at
    #: exactly 0.2mm track + 0.2mm clearance = 0.4mm pitch in the J1 corridor,
    #: so this is the one knob that changes how many lanes fit: 0.127mm (5 mil)
    #: drops the pitch to 0.327mm and buys a lane roughly every 2.4mm.
    ap.add_argument("--track-w", type=float, default=0.2)
    ap.add_argument("--via-dia", type=float, default=0.6)
    ap.add_argument("--safety", type=float, default=0.0)
    ap.add_argument("--max-iter", type=int, default=5000)
    #: Simulate a rip-up without touching the board: drop other-net items in
    #: the listed nets (or every other net with --drop-all) whose position is
    #: inside --drop-box. Lets a candidate rip-up be tested for the cost of one
    #: flood instead of one board edit plus one route attempt.
    ap.add_argument("--drop-nets", nargs="*", default=None)
    ap.add_argument("--drop-all", action="store_true")
    ap.add_argument("--drop-box", nargs=4, type=float, default=None,
                    metavar=("X0", "Y0", "X1", "Y1"))
    #: Seed the flood from the net's *own remote copper* (its trunk) instead of
    #: from the J1 pad. The pad-side flood answers "can this net get out?"; the
    #: trunk-side flood answers the mirror question "how far can the trunk
    #: reach back towards J1, and what seals the other end of the corridor?".
    ap.add_argument("--seed-goals", action="store_true")
    #: Print an ASCII map of a mm rectangle: '#' copper (illegal), '.' reached
    #: free space, ' ' free but unreached, 'G' a goal cell, 'S' a seed cell.
    #: Numbers/letters are too coarse to reason about a 2mm pocket; 0.2mm per
    #: character shows the actual corridors.
    ap.add_argument("--map", nargs=4, type=float, default=None,
                    metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--map-layer", default="F.Cu")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    ds = board.GetDesignSettings()
    edge_clear = ds.m_CopperEdgeClearance / S
    keep = a.clearance + a.track_w / 2 + a.safety
    pad_keep = a.clearance + a.via_dia / 2 + a.safety
    edge_keep = edge_clear + a.track_w / 2 + a.safety
    via_edge_keep = edge_clear + a.via_dia / 2 + a.safety
    print(f"edge rule {edge_clear}mm | track {a.track_w:.3f}mm keep {keep:.3f} "
          f"| via {a.via_dia:.3f}mm keep {pad_keep:.3f} "
          f"| edge keep {edge_keep:.3f} | safety {a.safety}")
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

        if a.drop_box or a.drop_nets or a.drop_all:
            x0, y0, x1, y1 = a.drop_box or (-1e9, -1e9, 1e9, 1e9)
            keepd, dropped = [], 0
            for it in others:
                if isinstance(it, pcbnew.PAD):
                    keepd.append(it)        # pads never move
                    continue
                hit = (a.drop_all or (a.drop_nets
                                      and it.GetNetname() in a.drop_nets))
                if hit:
                    p = it.GetPosition()
                    px, py = p.x / S, p.y / S
                    if x0 <= px <= x1 and y0 <= py <= y1:
                        dropped += 1
                        continue
                keepd.append(it)
            print(f"  [rip-up sim] dropped {dropped} item(s) "
                  f"({len(others)} -> {len(keepd)})")
            others = keepd

        grid = NGrid(board, a.step, keep, edge_keep, pad_keep, via_edge_keep,
                     layers)
        grid.build(others)

        pp = pad.GetPosition()
        si, sj = grid.ij(pp.x / S, pp.y / S)
        reach = {l: np.zeros((grid.ny, grid.nx), bool) for l in layers}

        # goals = the net's own copper, as cells (minus the J1 pad itself)
        goals = {l: np.zeros((grid.ny, grid.nx), bool) for l in layers}
        ng = 0
        pu = pad.m_Uuid.AsString()
        for it in own:
            if isinstance(it, pcbnew.PAD) and it.m_Uuid.AsString() == pu:
                continue
            sh = item_shape(it)
            if sh is None:
                continue
            cx, cy = (sh[0] + sh[2]) / 2, (sh[1] + sh[3]) / 2
            for l in layers:
                if on_layer(it, l):
                    i, j = grid.ij(cx, cy)
                    if 0 <= i < grid.nx and 0 <= j < grid.ny:
                        goals[l][j, i] = True
                        ng += 1

        n_start = 0
        n_goal_seed = 0
        seed_mask = {l: np.zeros((grid.ny, grid.nx), bool) for l in layers}
        if a.seed_goals:
            # Mirror question: seed from the far end of the net (its own trunk
            # and pads) and see how far it can reach *back* towards J1. Whatever
            # seals that region is what blocks the corridor from the north.
            for l in layers:
                reach[l] |= goals[l]
                seed_mask[l] |= goals[l]
                n_goal_seed += int(goals[l].sum())
            if not n_goal_seed:
                print(f"\n{name}: no remote copper to seed from")
                continue
        else:
            r = pad.GetBoundingBox()
            for di in range(-4, 5):
                for dj in range(-4, 5):
                    i, j = si + di, sj + dj
                    if not (0 <= i < grid.nx and 0 <= j < grid.ny):
                        continue
                    x, y = grid.xy(i, j)
                    if (r.GetLeft() / S <= x <= r.GetRight() / S
                            and r.GetTop() / S <= y <= r.GetBottom() / S):
                        reach[pcbnew.F_Cu][j, i] = True
                        seed_mask[pcbnew.F_Cu][j, i] = True
                        n_start += 1
            if not n_start:
                reach[pcbnew.F_Cu][sj, si] = True
                seed_mask[pcbnew.F_Cu][sj, si] = True
                n_start = 1

        src = "trunk" if a.seed_goals else "J1 pad"
        print(f"\n=== {name} === pad at ({pp.x/S:.3f},{pp.y/S:.3f}) "
              f"seed={src} {n_start or n_goal_seed} start cell(s), "
              f"{ng} goal cell(s), {len(others)} other-net item(s)")

        it = 0
        for it in range(a.max_iter):
            before = sum(int(x.sum()) for x in reach.values())
            for lay in layers:
                rr = reach[lay]
                for di, dj in NB8:
                    rr = spread(rr, grid.OK[lay], di, dj)
                reach[lay] = rr
            # layer change
            for k, lay in enumerate(layers):
                other = layers[1 - k]
                reach[other] |= reach[lay] & grid.VOK
            after = sum(int(x.sum()) for x in reach.values())
            if after == before:
                break
        print(f"  flooded {it + 1} iteration(s)")

        for lay in layers:
            rr = reach[lay]
            n = int(rr.sum())
            tag = "F.Cu" if lay == pcbnew.F_Cu else "B.Cu"
            if not n:
                print(f"  {tag}: 0 cell(s)")
                continue
            js, iss = np.nonzero(rr)
            x0, y0 = grid.xy(iss.min(), js.min())
            x1, y1 = grid.xy(iss.max(), js.max())
            hit = int((rr & goals[lay]).sum())
            print(f"  {tag}: {n:6d} cell(s)  "
                  f"x[{x0:.2f},{x1:.2f}] y[{y0:.2f},{y1:.2f}]  "
                  f"{hit} goal cell(s) inside")

        # what owns the walls
        walls = defaultdict(lambda: [0, 1e9])
        per_item = defaultdict(lambda: [0, 1e9])
        for lay in layers:
            rr = reach[lay]
            tag = "F.Cu" if lay == pcbnew.F_Cu else "B.Cu"
            illegal = ~grid.OK[lay]
            for di, dj in NB8:
                near = shift(rr, di, dj) & illegal
                if not near.any():
                    continue
                js, iss = np.nonzero(near)
                own_idx = grid.OWN[lay][js, iss]
                dd = grid.D[lay][js, iss]
                for o, d in zip(own_idx, dd):
                    if o < 0:
                        continue
                    key = (others[o].GetNetname(), tag)
                    walls[key][0] += 1
                    if float(d) < walls[key][1]:
                        walls[key][1] = float(d)
                    per_item[(int(o), tag)][0] += 1
                    if float(d) < per_item[(int(o), tag)][1]:
                        per_item[(int(o), tag)][1] = float(d)
        print(f"  pocket walls ({len(walls)} net/layer combos):")
        agg = defaultdict(lambda: [0, 1e9])
        for (net, tag), (cells, worst) in walls.items():
            agg[net][0] += cells
            agg[net][1] = min(agg[net][1], worst)
        for net, (cells, worst) in sorted(agg.items(),
                                          key=lambda kv: -kv[1][0])[:18]:
            print(f"     {net:<10} {cells:5d} wall cell(s)  "
                  f"closest {worst:+.3f}mm")

        print(f"  wall items by kind ({len(per_item)} distinct):")
        kinds = defaultdict(int)
        for (o, tag) in per_item:
            it = others[o]
            kinds["pad" if isinstance(it, pcbnew.PAD)
                  else "via" if isinstance(it, pcbnew.PCB_VIA)
                  else "trk"] += 1
        print(f"     " + "  ".join(f"{k}:{v}" for k, v in sorted(kinds.items())))
        top = sorted(per_item.items(), key=lambda kv: -kv[1][0])[:14]
        for (o, tag), (cells, worst) in top:
            it = others[o]
            p = it.GetPosition()
            kind = ("pad" if isinstance(it, pcbnew.PAD)
                    else "via" if isinstance(it, pcbnew.PCB_VIA) else "trk")
            extra = ""
            if kind == "trk":
                s, e = it.GetStart(), it.GetEnd()
                extra = (f" ({s.x/S:.2f},{s.y/S:.2f})->"
                         f"({e.x/S:.2f},{e.y/S:.2f}) w{it.GetWidth()/S:.3f}")
            elif kind == "pad":
                bb = it.GetBoundingBox()
                extra = (f" x[{bb.GetLeft()/S:.2f},{bb.GetRight()/S:.2f}]"
                         f" y[{bb.GetTop()/S:.2f},{bb.GetBottom()/S:.2f}]")
            print(f"     {cells:5d} cells {tag} {kind:<3} "
                  f"{it.GetNetname():<8} @({p.x/S:.2f},{p.y/S:.2f}) "
                  f"gap {worst:+.3f}{extra}")

        if a.map:
            lay = pcbnew.F_Cu if a.map_layer == "F.Cu" else pcbnew.B_Cu
            x0, y0, x1, y1 = a.map
            i0, j0 = grid.ij(x0, y0)
            i1, j1 = grid.ij(x1, y1)
            i0, i1 = max(0, min(i0, i1)), min(grid.nx - 1, max(i0, i1))
            j0, j1 = max(0, min(j0, j1)), min(grid.ny - 1, max(j0, j1))
            print(f"\n  map {a.map_layer} "
                  f"x[{x0:.2f},{x1:.2f}] y[{y0:.2f},{y1:.2f}] "
                  f"({i1-i0+1}x{j1-j0+1} cells @{a.step}mm)"
                  f"  #=copper .=reached ' '=free G=own-copper S=seed")
            hdr = "        " + "".join(
                str(int((grid.xy(i, j0)[0]) // 10) % 10) for i in range(i0, i1 + 1))
            print(hdr)
            for j in range(j0, j1 + 1):
                row = []
                for i in range(i0, i1 + 1):
                    if seed_mask[lay][j, i]:
                        row.append("S")
                    elif goals[lay][j, i]:
                        row.append("G")
                    elif not grid.OK[lay][j, i]:
                        row.append("#")
                    elif reach[lay][j, i]:
                        row.append(".")
                    else:
                        row.append(" ")
                print(f"  {grid.xy(i0, j)[1]:7.2f} " + "".join(row))


if __name__ == "__main__":
    main()
