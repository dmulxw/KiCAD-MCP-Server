"""How wide is the channel the 595 bundle actually has to fit through?

Every ROW/CSEL net is brand new and every one of them has to run west from a
SOIC output (x 53..94) to a J8/J10 pin (x 2..50).  The router converges on
exactly 14 of the 31 no matter how many repair rounds it is given, which reads
like a capacity ceiling -- but "reads like" is not a measurement.

Measure it.  For a representative net, take the router's own blocked mask and
sweep the strip band by band: for each row of grid cells, the widest run of
cells that is free on a layer, and the total free count.  A track needs a free
run at least wide enough to hold it plus CLEAR on both sides, so the widest run
per band divided by the track pitch is that band's lane count.

    python _probe_chan.py ROW6
"""
import sys, os

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import numpy as np
import pcbnew

import route as R

S = 1e6


def runs(row):
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


def main():
    net = sys.argv[1] if len(sys.argv) > 1 else "ROW6"
    board = pcbnew.LoadBoard(R.BOARD)
    router = R.Router(board)
    R.absorb(board, router)

    hw = R.WIDTHS.get(net, R.DEFAULT_W) / 2.0
    # Pitch a lane occupies: its own copper plus the clearance it must hold off
    # its neighbour, which is the same CLEAR the raster already used.
    pitch = (2 * hw + R.CLEAR) / R.GRID
    print("net=%s  hw=%.2f  CLEAR=%.2f  one lane = %.1f cells (%.2f mm)"
          % (net, hw, R.CLEAR, pitch, pitch * R.GRID), flush=True)

    # Union the masks of every net in the bundle: the question is not what one
    # net can reach, it is what the bundle as a whole has to share.
    bundle = sorted(R.ONLY)
    blocked = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
    for n in bundle:
        if n == net:
            continue
        b, _v = router.blocked_for(n, hw)
        blocked |= b
    print("bundle: %d nets, OBSTACLES = every other net's copper/pads\n"
          % len(bundle), flush=True)

    print("  y     layer  free  widest-run  lanes  x-range of widest run")
    for j in range(int(58.0 / R.GRID), int(74.0 / R.GRID) + 1):
        y = j * R.GRID
        for l, lname in ((0, "F.Cu"), (1, "B.Cu")):
            row = ~blocked[l, :, j]
            rs = runs(row)
            if not rs:
                continue
            w = max(rs)
            # where the widest run sits
            n = 0
            x0 = 0
            for i, v in enumerate(row):
                if v:
                    n += 1
                    if n == w:
                        x0 = i - w + 1
                        break
                else:
                    n = 0
            lanes = int(w // pitch)
            print("  %5.1f  %-4s  %5d  %6.1f mm  %5d  %.1f..%.1f"
                  % (y, lname, int(row.sum()), w * R.GRID, lanes,
                     x0 * R.GRID, (x0 + w) * R.GRID), flush=True)
        print()


if __name__ == "__main__":
    main()
