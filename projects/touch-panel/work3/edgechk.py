"""What is actually filling this board?

``edge.py`` reported no 8mm clear vertical run anywhere, which is a strong
claim about a 71 x 150mm board and worth checking before it is believed. The
histogram backs it up -- only 3.3% of cells clear 1.05mm on BOTH layers -- so
the question becomes *what* is filling it.

A 210-key capacitive touch panel is mostly electrode: if each key carries a
large sense pad on F.Cu then the front layer is copper almost everywhere, and
no through-hole part can clear both layers no matter where it is placed.
This prints the biggest pads, the two layers' clearance separately, and the
longest runs that respect the edge rule -- which is the number that decides
whether a header fits and how big it can be.

    python edgechk.py <board> [--need 1.05] [--edge 1.35]
"""

import argparse

import numpy as np
import pcbnew

from probe import NGrid

S = 1e6


def longest_runs(mask):
    """Every vertical run of True, longest first, as (cells, i, j0, j1)."""
    ny, nx = mask.shape
    out = []
    for i in range(nx):
        col = mask[:, i]
        j = 0
        while j < ny:
            if not col[j]:
                j += 1
                continue
            k = j
            while k + 1 < ny and col[k + 1]:
                k += 1
            out.append((k - j + 1, i, j, k))
            j = k + 1
    out.sort(key=lambda r: r[0], reverse=True)
    return out


def report(tag, mask, grid, step, top=5):
    runs = longest_runs(mask)
    if not runs:
        print(f"  {tag}: NO run at all")
        return
    print(f"  {tag}: longest {runs[0][0] * step:.2f}mm")
    for cells, i, j0, j1 in runs[:top]:
        print(f"      x={grid.x0 + i * step:7.2f}  "
              f"y {grid.y0 + j0 * step:7.2f}..{grid.y0 + j1 * step:7.2f}  "
              f"{cells * step:6.2f}mm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--need", type=float, default=1.05,
                    help="clearance a 1.7mm pad centre needs (0.85 + 0.2)")
    ap.add_argument("--edge", type=float, default=1.35,
                    help="distance from outline a pad centre needs")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.src)
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    grid = NGrid(board, a.step, 0.3, 0.6, 0.5, 0.7, layers)

    tracks = list(board.GetTracks())
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    print(f"{len(tracks)} track(s), {len(pads)} pad(s)")

    # PAD::GetParent() hands back a BOARD_ITEM_CONTAINER, not the FOOTPRINT, so
    # the owner reference has to be carried alongside rather than asked for.
    owner = {id(p): fp.GetReference()
             for fp in board.GetFootprints() for p in fp.Pads()}

    print("\nlargest pads by bounding box:")
    big = []
    for p in pads:
        bb = p.GetBoundingBox()
        big.append((bb.GetWidth() / S * bb.GetHeight() / S, p, bb))
    big.sort(key=lambda t: t[0], reverse=True)
    for area, p, bb in big[:10]:
        print(f"  {area:8.2f}mm2  {bb.GetWidth()/S:5.2f} x "
              f"{bb.GetHeight()/S:5.2f}  net {p.GetNetname()!r}  "
              f"{owner.get(id(p), '?')}.{p.GetNumber()}  "
              f"F={bool(p.IsOnLayer(pcbnew.F_Cu))} "
              f"B={bool(p.IsOnLayer(pcbnew.B_Cu))}")

    grid.build(tracks + pads)
    dF, dB = grid.D[layers[0]], grid.D[layers[1]]
    clr = np.minimum(dF, dB)

    print("\ncopper coverage (cells inside copper, D <= 0):")
    for nm, D in (("F.Cu", dF), ("B.Cu", dB), ("both", clr)):
        print(f"  {nm:>5}: {100.0 * (D <= 0).mean():5.1f}%")

    print(f"\ncells clear of copper by at least (F alone / B alone / both):")
    for t in (0.2, 0.5, 0.8, 1.05, 1.5):
        print(f"  {t:4.2f}mm:  F {100.0*(dF>=t).mean():5.2f}%   "
              f"B {100.0*(dB>=t).mean():5.2f}%   "
              f"both {100.0*(clr>=t).mean():5.2f}%")

    print(f"\nlongest vertical runs, edge rule applied (>= {a.edge:.2f}mm "
          f"from outline), clearance >= {a.need:.2f}mm:")
    eg = grid.EG >= a.edge
    report("F only ", (dF >= a.need) & eg, grid, a.step)
    report("B only ", (dB >= a.need) & eg, grid, a.step)
    report("both   ", (clr >= a.need) & eg, grid, a.step)

    print("\nhow much do the two rules each cost?")
    print(f"  clearance rule alone, no edge rule: "
          f"{(clr >= a.need).sum() * a.step * a.step:.0f} mm2 free")
    print(f"  edge rule alone, no clearance rule: "
          f"{eg.sum() * a.step * a.step:.0f} mm2 inside")
    print(f"  both: {(clr >= a.need).__and__(eg).sum() * a.step * a.step:.0f} mm2")


if __name__ == "__main__":
    main()
