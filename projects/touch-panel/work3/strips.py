"""Is the edge strip actually free, and is there anywhere to cut a window?

``recon.py`` showed the electrodes stop 4.25mm short of each side edge, which
sounds like exactly the gutter a 1x20 header needs. But "no electrode" is not
"no copper": the J1 fan-out, 220 MOSFETs, 31 resistors and 10 test points all
live somewhere on this board, and a through-hole header needs BOTH layers
clear along its whole length.

So measure the real occupancy of the two side gutters, cell by cell, on both
layers -- and separately answer the second half of the instruction, which is
whether the electrode array leaves any interior region open enough to cut a
viewport through. The array spans x 104.20..166.80 by y 108.50..241.50, which
is most of the board, so where a window could go is not obvious.

    python strips.py <board> [--pitch 2.54]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--pitch", type=float, default=2.54)
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.src)
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    bb = board.GetBoardEdgesBoundingBox()
    x0, x1 = bb.GetLeft() / S, bb.GetRight() / S
    y0, y1 = bb.GetTop() / S, bb.GetBottom() / S

    grid = NGrid(board, a.step, 0.3, 0.6, 0.5, 0.7, layers)
    tracks = list(board.GetTracks())
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    grid.build(tracks + pads)
    dF, dB = grid.D[layers[0]], grid.D[layers[1]]
    clr = np.minimum(dF, dB)

    print(f"grid {grid.nx} x {grid.ny} at {a.step}mm")

    # --- where does everything live? ---------------------------------------
    print("\nfootprint clusters (position spread):")
    for pre in ("Q", "R", "TP"):
        pts = [(fp.GetReference(), fp.GetPosition().x / S, fp.GetPosition().y / S,
                fp.GetLayerName())
               for fp in board.GetFootprints()
               if "".join(c for c in fp.GetReference() if not c.isdigit()) == pre]
        if not pts:
            continue
        px = [p[1] for p in pts]
        py = [p[2] for p in pts]
        lay = {}
        for p in pts:
            lay[p[3]] = lay.get(p[3], 0) + 1
        print(f"  {pre:<3} {len(pts):4d}  x {min(px):7.2f}..{max(px):7.2f}  "
              f"y {min(py):7.2f}..{max(py):7.2f}  {lay}")

    # --- the two side gutters ----------------------------------------------
    # A through-hole row needs a strip of width ~pad diameter; along its length
    # every cell must clear copper on both layers, and the pad centre must sit
    # inside the copper-to-edge rule.
    eg = grid.EG >= 0.5 + 0.1          # edge rule for a 0.2mm-radius feature
    print(f"\nside gutters, cells clear on BOTH layers "
          f"(>= {a.step}mm resolution):")
    for name, gx0, gx1 in (("left ", x0, 104.20), ("right", 166.80, x1)):
        i0 = max(0, int((gx0 - grid.x0) / a.step))
        i1 = min(grid.nx, int((gx1 - grid.x0) / a.step))
        sub = clr[:, i0:i1]
        print(f"  {name} x[{gx0:.2f},{gx1:.2f}] = {(gx1-gx0):.2f}mm wide, "
              f"{sub.shape[1]} cols")
        for t in (0.2, 0.5, 0.7, 0.85, 1.05):
            pct = 100.0 * (sub >= t).mean()
            print(f"      clear >= {t:4.2f}mm: {pct:5.1f}% of the gutter")

    # The number that decides a header: the longest run of a corridor of width
    # >= 2.0mm (one pin row plus clearance) anywhere in the gutter.
    print("\nlongest vertical corridor of width >= 2.0mm in each gutter "
          "(both layers):")
    for name, gx0, gx1 in (("left ", x0, 104.20), ("right", 166.80, x1)):
        i0 = max(0, int((gx0 - grid.x0) / a.step))
        i1 = min(grid.nx, int((gx1 - grid.x0) / a.step))
        ok = (clr >= 0.85) & eg
        runs = longest_runs(ok[:, i0:i1])
        if not runs:
            print(f"  {name}: none")
            continue
        cells, i, j0, j1 = runs[0]
        wires = 2.0 / a.step
        # widen: how many adjacent columns from i share a run this long?
        width = 1
        for di in range(1, 60):
            for j in range(j0, j1 + 1):
                if i + di >= ok.shape[1] or not ok[j, i0 + i + di]:
                    break
            else:
                width += 1
                continue
            break
        ln = cells * a.step
        print(f"  {name}: longest {ln:6.2f}mm at x="
              f"{grid.x0 + (i0+i)*a.step:7.2f}  "
              f"y {grid.y0 + j0*a.step:7.2f}..{grid.y0 + j1*a.step:7.2f}  "
              f"({int((ln - 1.7) // a.pitch) + 1} x {a.pitch}mm pins)")

    # --- can a window be cut anywhere inside? -------------------------------
    print("\nlargest interior region with NO copper on either layer, "
          "clear of the outline by >= 2mm:")
    inner = np.zeros_like(clr, dtype=bool)
    m = 2.0
    im0 = int((x0 + m - grid.x0) / a.step)
    im1 = int((x1 - m - grid.x0) / a.step)
    jm0 = int((y0 + m - grid.y0) / a.step)
    jm1 = int((y1 - m - grid.y0) / a.step)
    inner[jm0:jm1, im0:im1] = True
    free = (clr > 0) & inner
    print(f"  free cells inside a 2mm margin: {free.sum()} "
          f"({free.sum() * a.step * a.step:.1f} mm2)")
    # crude blob report: rows of the array that are largely free
    rows = free.sum(axis=1)
    solid = np.where(rows > 0.5 * (im1 - im0))[0]
    if len(solid):
        print(f"  rows that are >50% free: {len(solid)} "
              f"(y {grid.y0 + solid[0]*a.step:.2f} .. "
              f"{grid.y0 + solid[-1]*a.step:.2f})")
    else:
        print("  no row is even 50% free -- the copper is spread across "
              "the whole interior")


if __name__ == "__main__":
    main()
