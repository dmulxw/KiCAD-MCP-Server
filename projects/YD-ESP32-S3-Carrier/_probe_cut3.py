"""Where is the throat for the westward bus, measured as packing capacity.

Every ROW*/CSEL* net runs east->west: a 74HC595 output pad in the strip
(x 53..94, y 64..72) to a J8/J10 header pin (x 2..37).  So the binding question
is not "is the strip empty" (it is) but "how many 0.30 mm traces with 0.16 mm
clearance fit through a vertical cut at x".

Packing, not run-length-counting: a gap of G mm holds N traces where
    N*w + (N-1)*c <= G   ->   N = floor((G + c) / (w + c))
Gaps are measured from a mask of EVERYTHING physical -- frozen copper, vias,
and all pads including the bundle's own (a pad is copper; it consumes area
whether or not its net is ours).

Prints the capacity profile over x so the minimum is the real throat.

    python _probe_cut3.py
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import pcbnew

import route as R

BAK = R.BOARD + ".pre-route595.bak"
TMP = os.path.join(os.path.dirname(R.BOARD), "_cut3_tmp.kicad_pcb")

W = R.DEFAULT_W          # 0.30 mm
C = R.CLEAR              # 0.16 mm
Y0, Y1 = 58.0, 74.0      # the band the bus must traverse
NPL = 2                  # layers


def runs_len(row):
    out, n = [], 0
    for v in row:
        if v:
            n += 1
        elif n:
            out.append(n)
            n = 0
    if n:
        out.append(n)
    return out


def capacity(m, i, j0, j1):
    """Traces fitting through one grid column i, both layers."""
    total = 0
    for l in range(NPL):
        for n in runs_len(~m[l, i, j0:j1]):
            gap = n * R.GRID
            if gap >= W:
                total += int((gap + C) / (W + C))
    return total


def main():
    shutil.copyfile(BAK, TMP)
    board = pcbnew.LoadBoard(TMP)
    router = R.Router(board)
    R.absorb(board, router)
    R.rip(router, set(router.pads))

    # mask: every physical object, bundle included
    m = router.edge.copy()
    tr_r = R.CLEAR / 2.0
    for _net, kind, a, layers in router.shapes:
        for layer in layers:
            if kind == "circle":
                R.raster_circle(m, layer, a[0], a[1], a[2] + tr_r)
            else:
                R.raster_rect(m, layer, a[0], a[1], a[2], a[3], tr_r)
    for _n, layer, x1, y1, x2, y2, w in router.frozen:
        R.raster_seg(m, layer, x1, y1, x2, y2, w / 2.0 + tr_r)
    for _n, vx, vy in router.frozen_vias:
        for layer in range(NPL):
            R.raster_circle(m, layer, vx, vy, R.VIA_D / 2.0 + tr_r)

    print("frozen: %d seg(s), %d via(s)   band y=%.0f..%.0f\n"
          % (len(router.frozen), len(router.frozen_vias), Y0, Y1), flush=True)

    j0, j1 = int(Y0 / R.GRID), int(Y1 / R.GRID)
    prof = [(capacity(m, i, j0, j1), i * R.GRID) for i in range(R.NX)]

    cap, xmin = min(prof)
    print("THROAT: %d lane(s) at x=%.1f mm" % (cap, xmin))
    order = sorted(prof, key=lambda t: t[0])[:8]
    print("tightest columns: "
          + ", ".join("%d@x=%.0f" % (c, x) for c, x in order))
    print()

    step = max(1, int(2.0 / R.GRID))
    line = ["%.0f:%d" % (i * R.GRID, capacity(m, i, j0, j1))
            for i in range(0, R.NX, step)]
    print("profile x=0..100 every 2 mm (lanes):")
    for k in range(0, len(line), 10):
        print("   " + "  ".join(line[k:k + 10]))

    # separate the two constraints: east of the headers vs the pad rows
    east = [(c, x) for c, x in prof if x >= 45.0]
    west = [(c, x) for c, x in prof if 2.0 <= x < 45.0]
    print()
    print("min x>=45 (strip / 595 pad rows): %d at x=%.1f" % min(east))
    print("min  2<=x<45 (header side)      : %d at x=%.1f" % min(west))

    os.remove(TMP)


if __name__ == "__main__":
    main()
