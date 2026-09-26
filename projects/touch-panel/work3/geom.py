"""Pin down the electrode geometry, and whether a window fits anywhere.

Two questions the redesign turns on.

1. What exactly is an electrode? ``strips.py`` implies each PAD net carries a
   5.00 x 5.00mm sense pad plus a much smaller connection pad, on a 6.40mm
   x/y pitch. If that is right, the array is a 10 x 21 grid with only 1.40mm
   between neighbours -- which settles the window question by itself, because
   a cutout in the interior can be at most 1.4mm across.

2. Is there any contiguous copper-free region big enough to cut a viewport?
   ``fill.py`` said the largest both-layer free rectangle is 9.20 x 2.20mm,
   but that was measured with a 1.05mm pad-clearance rule. A *cutout* only
   needs the copper gone, so re-measure with no clearance rule at all. That
   is the most generous possible answer, and if it still fails, it fails.

Also dumps every text item -- if the mechanical window is documented anywhere
in the design, it will be a silkscreen or fab note.

    python geom.py <board>
"""

import argparse
from collections import defaultdict

import numpy as np
import pcbnew

from probe import NGrid

S = 1e6


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


def downsample(mask, k):
    ny, nx = mask.shape
    ny2, nx2 = ny // k, nx // k
    return mask[:ny2 * k, :nx2 * k].reshape(ny2, k, nx2, k).all(axis=(1, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=float, default=0.05)
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.src)
    pads = [(fp, p) for fp in board.GetFootprints() for p in fp.Pads()]

    # --- 1. what is an electrode? ------------------------------------------
    shapes = defaultdict(int)
    for fp, p in pads:
        if not p.GetNetname().startswith("PAD"):
            continue
        sz = p.GetSize()
        lay = ("F" if p.IsOnLayer(pcbnew.F_Cu) else "") + \
              ("B" if p.IsOnLayer(pcbnew.B_Cu) else "")
        shapes[(round(sz.x / S, 3), round(sz.y / S, 3), lay)] += 1
    print("electrode pad shapes (w x h mm, layers) -> count:")
    for k, v in sorted(shapes.items(), key=lambda t: -t[1]):
        print(f"  {k[0]:6.3f} x {k[1]:6.3f}  layers {k[2]:<2}  {v:5d}")

    # grouping: does each net really have one big + one small pad?
    per_net = defaultdict(list)
    for fp, p in pads:
        if p.GetNetname().startswith("PAD"):
            sz = p.GetSize()
            per_net[p.GetNetname()].append((round(sz.x / S, 2),
                                            round(sz.y / S, 2)))
    k = sorted(per_net)[0]
    print(f"\nsample nets: {k} -> {sorted(per_net[k])}, "
          f"{sorted(per_net)[100]} -> {sorted(per_net[sorted(per_net)[100]])}")

    # big sense pads only
    sense = [(fp, p) for fp, p in pads
             if p.GetNetname().startswith("PAD")
             and round(p.GetSize().x / S, 2) >= 4.0]
    if sense:
        xs = sorted({round(p.GetPosition().x / S, 2) for _, p in sense})
        ys = sorted({round(p.GetPosition().y / S, 2) for _, p in sense})
        print(f"\nsense pads: {len(sense)}")
        print(f"  x centres ({len(xs)}): {[round(v,2) for v in xs]}")
        print(f"  y centres ({len(ys)}): first {ys[:4]} last {ys[-2:]}")
        if len(xs) > 1:
            print(f"  x pitch {xs[1]-xs[0]:.3f} -> gap "
                  f"{xs[1]-xs[0] - sense_wide(sense, xs[0]):.3f}mm between pads")
        if len(ys) > 1:
            print(f"  y pitch {ys[1]-ys[0]:.3f} -> gap "
                  f"{ys[1]-ys[0] - sense_wide(sense, xs[0]):.3f}mm between pads")

    # --- 2. biggest copper-free rectangle, no clearance rule ----------------
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    grid = NGrid(board, a.step, 0.3, 0.6, 0.5, 0.7, layers)
    grid.build(list(board.GetTracks()) + [p for _, p in pads])
    dF, dB = grid.D[layers[0]], grid.D[layers[1]]
    clr = np.minimum(dF, dB)
    free = clr > 0            # strictly: not inside any copper on either layer

    bb = board.GetBoardEdgesBoundingBox()
    x0, x1 = bb.GetLeft() / S, bb.GetRight() / S
    y0, y1 = bb.GetTop() / S, bb.GetBottom() / S
    m = 2.0
    inner = np.zeros_like(free)
    inner[int((y0 + m - grid.y0) / a.step):int((y1 - m - grid.y0) / a.step),
          int((x0 + m - grid.x0) / a.step):int((x1 - m - grid.x0) / a.step)] = True
    k = 4
    _, i0, j0, i1, j1 = max_rect(downsample(free & inner, k))
    print(f"\nlargest copper-free rectangle inset >= {m}mm from the outline:")
    print(f"  {(i1-i0)*k*a.step:6.2f} x {(j1-j0)*k*a.step:6.2f} mm  at "
          f"x {grid.x0 + i0*k*a.step:.2f}  y {grid.y0 + j0*k*a.step:.2f}")
    print("  (no clearance rule applied -- this is the theoretical maximum "
          "for a cutout)")

    # --- 3. any text that documents the mechanics? -------------------------
    print("\ntext items on the board:")
    n = 0
    for d in board.GetDrawings():
        if d.GetClass() != "PCB_TEXT":
            continue
        n += 1
        print(f"  {d.GetLayerName():<8} {str(d.GetText())[:60]!r}")
    for fp in board.GetFootprints():
        for it in fp.GraphicalItems():
            if it.GetClass() != "FP_TEXT":
                continue
            t = str(it.GetText())
            if t in ("REF**", "") or t.startswith("${"):
                continue
            n += 1
            print(f"  {it.GetLayerName():<8} {t[:60]!r}  ({fp.GetReference()})")
    print(f"  total {n}")


def sense_wide(sense, xc):
    for _, p in sense:
        if abs(p.GetPosition().x / S - xc) < 0.01:
            return p.GetSize().x / S
    return 0.0


if __name__ == "__main__":
    main()
