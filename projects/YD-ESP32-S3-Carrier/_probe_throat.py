"""Is there a hard ceiling on how many of the 39 new nets can cross, or not?

Every strategy knob swept so far (ORDER, VIA_COST, BLOCK_LIMIT, CROWD_COST)
lands on 20-23 of 39, and that convergence is suspicious.  Two readings:

  * a *strategy* gap -- each setting grabs a different 23, so a better search
    would get more; or
  * a hard *throat* -- some horizontal line across the board is crossed by only
    N lanes of free space once the pre-existing copper is accounted for, and no
    router, however clever, can push 39 nets through N lanes.

The two call for opposite responses, so measure instead of guessing.  For each
grid row, count the free lanes a bundle track could occupy: every contiguous
free run divided by the track pitch (its own copper plus the clearance it must
hold off its neighbour).  Summing per run, not taking the widest, is the point
-- capacity across a line is all the runs together.  The minimum over y is the
throat.

Bundle copper is deliberately EXCLUDED from the mask: the question is what the
pre-existing board leaves for the new nets, so the new nets must not block
themselves.  Their pads are reported separately, since pads are physical and do
consume area even though the tracks are what we are counting.

    python _probe_throat.py
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import numpy as np
import pcbnew

import route as R

BAK = R.BOARD + ".pre-route595.bak"
TMP = os.path.join(os.path.dirname(R.BOARD), "_throat_tmp.kicad_pcb")


def runs_len(row):
    """Lengths of the contiguous True runs in a 1-D bool array."""
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


def corridor(router, bundle, hw, with_bundle_pads):
    """Mask of everything the bundle must squeeze past, per layer."""
    m = router.edge.copy()
    tr_r = R.CLEAR + hw

    for other, kind, a, layers in router.shapes:
        # A bundle pad still occupies copper.  Counted only on request, so the
        # two runs bracket the answer instead of hiding behind one choice.
        if other in bundle and not with_bundle_pads:
            continue
        for layer in layers:
            if kind == "circle":
                R.raster_circle(m, layer, a[0], a[1], a[2] + tr_r)
            else:
                R.raster_rect(m, layer, a[0], a[1], a[2], a[3], tr_r)

    for onet, layer, x1, y1, x2, y2, w in router.frozen:
        if onet in bundle:
            continue
        R.raster_seg(m, layer, x1, y1, x2, y2, w / 2.0 + tr_r)
    for vnet, vx, vy in router.frozen_vias:
        if vnet in bundle:
            continue
        for layer in (0, 1):
            R.raster_circle(m, layer, vx, vy, R.VIA_D / 2.0 + tr_r)
    return m


def lanes(m, j, pitch):
    """Total lane capacity across grid row j, both layers."""
    total = 0
    for l in (0, 1):
        for n in runs_len(~m[l, :, j]):
            total += int(n // pitch)
    return total


def main():
    bundle = set(R.ONLY)
    hw = R.WIDTHS.get("ROW1", R.DEFAULT_W) / 2.0
    pitch = (2 * hw + R.CLEAR) / R.GRID
    print("bundle=%d nets  hw=%.2f  pitch=%.1f cells (%.2f mm)\n"
          % (len(bundle), hw, pitch, pitch * R.GRID), flush=True)

    shutil.copyfile(BAK, TMP)          # LoadBoard refuses any name but .kicad_pcb
    board = pcbnew.LoadBoard(TMP)
    router = R.Router(board)
    R.absorb(board, router)
    R.rip(router, set(router.pads))    # bare: our copper gone, frozen stays
    print("frozen: %d seg(s), %d via(s)\n"
          % (len(router.frozen), len(router.frozen_vias)), flush=True)

    for tag, wb in (("frozen only     ", False), ("frozen + new pads", True)):
        m = corridor(router, bundle, hw, wb)
        prof = [(lanes(m, j, pitch), j) for j in range(R.NY)]
        cap, jmin = min(prof)
        print("--- %s : throat %d lane(s) at y=%.1f" % (tag, cap, jmin * R.GRID),
          flush=True)
        # the band that matters: everything between the SOIC row and the south edge
        band = [(c, j) for (c, j) in prof if 50.0 <= j * R.GRID <= 74.0]
        bcap, bj = min(band)
        print("    min over y 50..74 : %d lane(s) at y=%.1f" % (bcap, bj * R.GRID),
          flush=True)
        # where it is roomy, for contrast
        wide = sorted(prof, reverse=True)[:3]
        print("    roomiest rows     : "
              + ", ".join("%d lanes @y=%.1f" % (c, j * R.GRID) for c, j in wide),
          flush=True)
        # the profile through the corridor, thinned to every 1 mm
        print("    profile y=50..74 (lanes):", flush=True)
        line = []
        for j in range(int(50.0 / R.GRID), R.NY, int(1.0 / R.GRID)):
            line.append("%.0f:%d" % (j * R.GRID, lanes(m, j, pitch)))
        for k in range(0, len(line), 8):
            print("      " + "  ".join(line[k:k + 8]), flush=True)
        print(flush=True)

    os.remove(TMP)


if __name__ == "__main__":
    main()
