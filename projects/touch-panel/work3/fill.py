"""What is the largest connector this board can physically accept?

``edge.py`` found a longest clear vertical run of 6.55mm where BOTH copper
layers clear a 1.7mm pad, against the 100.76mm a 1x40 header needs. Before
accepting that, it is worth knowing what is eating the board -- and what the
biggest free area actually is, since that is the number that sizes any
replacement part.

Two answers, because the two layers are not alike:

* cage a rectangle: a footprint needs a contiguous area, not a thin line, so
  the largest all-free axis-aligned rectangle is the real budget;
* census the copper: how many pads, how big, on which layer.

    python fill.py <board>
"""

import argparse
from collections import defaultdict

import numpy as np
import pcbnew

from probe import NGrid

S = 1e6


def downsample(mask, k):
    """AND k x k blocks -- a block is free only if every cell in it is free."""
    ny, nx = mask.shape
    ny2, nx2 = ny // k, nx // k
    return mask[:ny2 * k, :nx2 * k].reshape(ny2, k, nx2, k).all(axis=(1, 3))


def max_rect(m):
    """Largest all-True axis-aligned rectangle: (area, x0, y0, x1, y1)."""
    ny, nx = m.shape
    heights = np.zeros(nx, np.int32)
    best = (0, 0, 0, 0, 0)
    for j in range(ny):
        heights = np.where(m[j], heights + 1, 0)
        stack = []
        for i in range(nx + 1):
            h = int(heights[i]) if i < nx else 0
            start = i
            while stack and stack[-1][1] > h:
                si, sh = stack.pop()
                if sh * (i - si) > best[0]:
                    best = (sh * (i - si), si, j - sh + 1, i, j + 1)
                start = si
            stack.append((start, h))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--need", type=float, default=1.05)
    ap.add_argument("--edge", type=float, default=1.35)
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.src)
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    grid = NGrid(board, a.step, 0.3, 0.6, 0.5, 0.7, layers)

    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    bynet = defaultdict(lambda: [0, 0.0])
    for p in pads:
        bb = p.GetBoundingBox()
        e = bynet[p.GetNetname()]
        e[0] += 1
        e[1] += bb.GetWidth() / S * bb.GetHeight() / S
    elec = {n: v for n, v in bynet.items() if n.startswith("PAD")}
    print(f"electrode nets (PAD*): {len(elec)}")
    if elec:
        fp = sorted(elec.items(), key=lambda t: -t[1][1])[:3]
        for n, (cnt, area) in fp:
            print(f"  e.g. {n}: {cnt} pad(s), {area:.1f}mm2")
        print(f"  total electrode copper: "
              f"{sum(v[1] for v in elec.values()):.0f}mm2")
    print(f"board area: {(grid.bb[2]-grid.bb[0])*(grid.bb[3]-grid.bb[1]):.0f}mm2")

    grid.build(list(board.GetTracks()) + pads)
    dF, dB = grid.D[layers[0]], grid.D[layers[1]]
    clr = np.minimum(dF, dB)
    eg = grid.EG >= a.edge

    k = 4                      # 0.2mm blocks
    print(f"\nlargest free rectangle (pad centre must clear {a.need}mm "
          f"from copper, be {a.edge}mm inside the outline):")
    for tag, mask in (("F.Cu only", (dF >= a.need) & eg),
                      ("B.Cu only", (dB >= a.need) & eg),
                      ("BOTH layers", (clr >= a.need) & eg)):
        _, x0, y0, x1, y1 = max_rect(downsample(mask, k))
        w = (x1 - x0) * k * a.step
        h = (y1 - y0) * k * a.step
        print(f"  {tag:12} {w:6.2f} x {h:6.2f} mm   at "
              f"x {grid.x0 + x0*k*a.step:.2f}  y {grid.y0 + y0*k*a.step:.2f}")
        if tag != "F.Cu only":
            print(f"               -> widest 1xN row here: "
                  f"N <= {int(w // 2.54) + 1}, "
                  f"longest column: N <= {int(h // 2.54) + 1}")


if __name__ == "__main__":
    main()
