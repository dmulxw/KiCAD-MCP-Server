"""Where can a 40-pin 2.54mm header fit?

A 1x40 pin header spans 39 x 2.54 = 99.06mm plus a pad at each end, which is
longer than the board is wide (71.1mm). So it can only lie *along* an edge,
north to south, and only where a 100.8mm run is clear.

Clearance needed at each pin: the pad is 1.7mm across, so its edge must keep
the 0.2mm design clearance from any other net's copper -- 0.85 + 0.2 = 1.05mm
from the pad centre. And the pad has to sit inside the 0.5mm copper-to-edge
rule -- 0.85 + 0.5 = 1.35mm from the outline. A through-hole pad is on both
copper layers, so both layers must clear.

Prints every strip that satisfies both, longest first. That is where the
header has to go.

    python edge.py <board> [--pins 40] [--pitch 2.54]
"""

import argparse

import numpy as np
import pcbnew

from probe import NGrid

S = 1e6


def free_runs(mask):
    """Yield (j0, j1) inclusive index runs of True along a 1-D bool array."""
    out = []
    n = len(mask)
    j = 0
    while j < n:
        if not mask[j]:
            j += 1
            continue
        k = j
        while k + 1 < n and mask[k + 1]:
            k += 1
        out.append((j, k))
        j = k + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--pins", type=int, default=40)
    ap.add_argument("--pitch", type=float, default=2.54)
    ap.add_argument("--pad-r", type=float, default=0.85, help="pad half-width mm")
    ap.add_argument("--clear", type=float, default=0.2)
    ap.add_argument("--edge", type=float, default=0.5)
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.src)
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]

    print("copper layer count:",
          board.GetCopperLayerCount())
    edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S

    grid = NGrid(board, a.step, 0.3, edge_clear + 0.1, 0.5, edge_clear + 0.3,
                 layers)
    items = list(board.GetTracks())
    for fp in board.GetFootprints():
        items += list(fp.Pads())
    grid.build(items)

    clr = np.minimum(grid.D[layers[0]], grid.D[layers[1]])
    need = a.pad_r + a.clear
    edge_need = a.pad_r + a.edge
    ok = (clr >= need) & (grid.EG >= edge_need)

    span = (a.pins - 1) * a.pitch + 2 * a.pad_r
    print(f"need clearance {need:.2f}mm from copper on BOTH layers, "
          f"{edge_need:.2f}mm from the outline")
    print(f"header footprint span needed: {span:.2f}mm\n")

    # Fiducials carry a 3mm keepout the user asked for; treat them as blockers
    # even though a header passing near one is electrically legal.
    fid = [(fp.GetPosition().x / S, fp.GetPosition().y / S)
           for fp in board.GetFootprints()
           if fp.GetReference().startswith("MK")]

    best = []
    for i in range(grid.nx):
        x = grid.x0 + i * a.step
        if not ok[:, i].any():
            continue
        for j0, j1 in free_runs(ok[:, i]):
            y0 = grid.y0 + j0 * a.step
            y1 = grid.y0 + j1 * a.step
            ln = y1 - y0
            if ln < 8.0:
                continue
            best.append((ln, x, y0, y1))

    best.sort(reverse=True)
    if not best:
        print("NO clear run of even 8mm exists on this board.")
        return

    longest = best[0][0]
    pins = int((longest - 2 * a.pad_r) // a.pitch) + 1
    print(f"longest clear run anywhere: {longest:.2f}mm "
          f"-> a 1x{pins} header is the most that fits "
          f"(need {span:.2f}mm for 1x{a.pins})\n")

    # Collapse to distinct regions: consecutive x values are the same slot.
    print(f"{'x':>8} {'y range':>20} {'run mm':>8} {'pins':>5}  nearest fiducial")
    shown = []
    for ln, x, y0, y1 in best:
        if any(abs(x - sx) < 2.0 and not (y1 < sy0 - 3 or y0 > sy1 + 3)
               for _, sx, sy0, sy1 in shown):
            continue
        shown.append((ln, x, y0, y1))
        d = min(((x - fx) ** 2 + (max(y0 - fy, fy - y1, 0)) ** 2) ** 0.5
                for fx, fy in fid) if fid else float("inf")
        np_ = int((ln - 2 * a.pad_r) // a.pitch) + 1
        print(f"{x:8.2f} {y0:8.2f}..{y1:<8.2f} {ln:8.2f} {np_:5d}  {d:.1f}mm")
        if len(shown) >= 25:
            break

    if not shown:
        print("no distinct region")


if __name__ == "__main__":
    main()
