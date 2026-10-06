"""Flood with A*'s exact movement rules and see how much of the board it gets.

_tp_why.py's flood allowed corner cutting, and A* does not -- `if di and dj and
(blk[..] or blk[..]): continue` -- and it gated vias on only one layer instead
of both.  In open space those rules never matter; in a dense board a diagonal
squeeze is exactly where they bind, which is why a flood can call two pads
connected while A* exhausts its heap.  This walks the same graph A* walks.
"""
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

NET = sys.argv[1] if len(sys.argv) > 1 else "ROW16"

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

w = R.WIDTHS.get(NET, R.DEFAULT_W)
blocked, via_blocked = rt.blocked_for(NET, w / 2.0)
pads = rt.pads[NET]

NX, NY, NL = R.NX, R.NY, R.NL
area = NX * NY
blk = bytearray(blocked.reshape(-1).tobytes())
vblk = bytearray(via_blocked.reshape(-1).tobytes())


def flood(seed_flat):
    seen = bytearray(area * NL)
    st = [k for k in seed_flat if not blk[k]]
    for k in st:
        seen[k] = 1
    n = len(st)
    while st:
        k = st.pop()
        l, rem = divmod(k, area)
        i, j = rem // NY, rem % NY
        base = l * area
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ni, nj = i + di, j + dj
            if ni < 0 or nj < 0 or ni >= NX or nj >= NY:
                continue
            nk = base + ni * NY + nj
            if blk[nk] or seen[nk]:
                continue
            if di and dj and (blk[base + (i + di) * NY + j]
                              or blk[base + i * NY + (j + dj)]):
                continue
            seen[nk] = 1
            st.append(nk)
            n += 1
        nb = (1 - l) * area + rem
        if (not seen[nb] and not blk[nb] and not vblk[k] and not vblk[nb]
                and rt.via_ok(R.mx(i), R.my(j))):
            seen[nb] = 1
            st.append(nb)
            n += 1
    return seen, n


def flat_of(entry):
    return [l * area + i * NY + j
            for l in (entry[3] or (0, 1)) for (i, j) in entry[2]]


print("%s   %d pad(s)" % (NET, len(pads)))
seed0 = flat_of(pads[0])
seen, n = flood(seed0)
print("A*-equivalent region from pad 0: %d cell(s)  (%.1f%% of the grid)"
      % (n, 100.0 * n / (area * NL)))
for k, (x, y, nodes, layers) in enumerate(pads):
    f = flat_of(pads[k])
    hit = sum(1 for q in f if seen[q])
    print("   pad %-3d (%8.3f,%8.3f)  %d/%d cell(s) in region   %s"
          % (k, x, y, hit, len(f), "OK" if hit else "SEALED"))

# and the other way round, to say which side the wall belongs to
print()
seed1 = flat_of(pads[1])
seen1, n1 = flood(seed1)
print("A*-equivalent region from pad 1: %d cell(s)" % n1)
hit0 = sum(1 for q in flat_of(pads[0]) if seen1[q])
print("   pad 0's cells inside pad 1's region: %d of %d"
      % (hit0, len(flat_of(pads[0]))))
