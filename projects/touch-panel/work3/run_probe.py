"""Drive probe.NGrid/astar for a set of nets and report the rip-up size."""
import argparse
from collections import defaultdict

import numpy as np
import pcbnew

from probe import INF, NGrid, astar, item_shape, on_layer

S = 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", nargs="*", required=True)
    ap.add_argument("--ref", default="J1")
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--clearance", type=float, default=0.2)
    ap.add_argument("--safety", type=float, default=0.0)
    ap.add_argument("--via-cost", type=float, default=25.0)
    ap.add_argument("--no-conflict", action="store_true")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    ds = board.GetDesignSettings()
    edge_clear = ds.m_CopperEdgeClearance / S
    keep = a.clearance + 0.2 / 2 + a.safety
    pad_keep = a.clearance + 0.6 / 2 + a.safety
    edge_keep = edge_clear + 0.2 / 2 + a.safety
    via_edge_keep = edge_clear + 0.6 / 2 + a.safety
    print(f"edge rule {edge_clear}mm -> keep {keep:.3f} (track) "
          f"{pad_keep:.3f} (via)  edge_keep {edge_keep:.3f}  safety {a.safety}")
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]

    j1 = next(fp for fp in board.GetFootprints() if fp.GetReference() == a.ref)

    for name in a.nets:
        own = [t for t in board.GetTracks() if t.GetNetname() == name]
        for fp in board.GetFootprints():
            own += [p for p in fp.Pads() if p.GetNetname() == name]
        pad = None
        for p in j1.Pads():
            if p.GetNetname() == name:
                pad = p
                break
        if pad is None:
            print(f"\n{name}: no {a.ref} pad")
            continue

        others = [t for t in board.GetTracks() if t.GetNetname() != name]
        for fp in board.GetFootprints():
            others += [p for p in fp.Pads() if p.GetNetname() != name]

        grid = NGrid(board, a.step, keep, edge_keep, pad_keep, via_edge_keep,
                     layers)
        grid.build(others)

        pp = pad.GetPosition()
        si, sj = grid.ij(pp.x / S, pp.y / S)
        r = pad.GetBoundingBox()
        start = []
        for di in range(-4, 5):
            for dj in range(-4, 5):
                i, j = si + di, sj + dj
                if not (0 <= i < grid.nx and 0 <= j < grid.ny):
                    continue
                x, y = grid.xy(i, j)
                if (r.GetLeft() / S <= x <= r.GetRight() / S
                        and r.GetTop() / S <= y <= r.GetBottom() / S):
                    start.append((pcbnew.F_Cu, i, j))
        if not start:
            start = [(pcbnew.F_Cu, si, sj)]

        goals = set()
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
                        goals.add((l, i, j))
        print(f"\n=== {name} === start {len(start)} cell(s), "
              f"{len(goals)} goal cell(s), {len(own)} own item(s)")

        path, crossing, expanded, closest = astar(
            grid, start, goals, a.via_cost, conflict=not a.no_conflict)

        if path is None:
            print(f"  NO PATH  (expanded {expanded}); "
                  f"closest approach {closest[0] * a.step:.2f}mm")
        else:
            nvia = sum(1 for k in range(1, len(path))
                       if path[k][0] != path[k - 1][0])
            ln = 0.0
            for k in range(1, len(path)):
                if path[k][0] == path[k - 1][0]:
                    dx = path[k][1] - path[k - 1][1]
                    dy = path[k][2] - path[k - 1][2]
                    ln += (dx * dx + dy * dy) ** 0.5 * a.step
            print(f"  PATH {len(path)} cells, {ln:.1f}mm, {nvia} via(s), "
                  f"expanded {expanded}")

        if crossing:
            print(f"  crosses {len(crossing)} other-net item(s):")
            agg = defaultdict(lambda: [0, 1e9, ""])
            for who, (cells, worst) in crossing.items():
                it = others[who]
                net = it.GetNetname()
                kind = ("pad" if isinstance(it, pcbnew.PAD)
                        else "via" if isinstance(it, pcbnew.PCB_VIA)
                        else "trk")
                agg[net][0] += cells
                agg[net][1] = min(agg[net][1], worst)
                agg[net][2] = kind
            for net, (cells, worst, kind) in sorted(
                    agg.items(), key=lambda kv: -kv[1][0]):
                print(f"     {net:<10} {cells:5d} cell(s)  "
                      f"worst gap {worst:+.3f}mm")


if __name__ == "__main__":
    main()
