"""Can each stranded net actually reach its partner -- and if not, how big is the
pocket it is stuck in?

route_all() reports *that* a pad could not be reached, which on this board is not
enough to act on.  A net fails for one of two very different reasons:

  * the whole approach is walled off -- the reachable set is tens of thousands of
    nodes and simply does not contain the target pad.  The channel is there but
    it does not lead where the net needs to go, so the fix is a corridor.
  * the pad sits in a small pocket -- a few hundred nodes, sealed on all sides.
    The fix is to move the part.

So: flood-fill from one pad's own nodes through exactly the mask blocked_for()
builds, allowing a layer change wherever a via would be legal, and report the size
of the reached set and which of the net's other pads are inside it.

The board is loaded and absorbed exactly as route.py's incremental pass does, so
the numbers describe the run that failed, not a hypothetical one.
"""
import importlib.util
import sys
from collections import deque

import numpy as np
import pcbnew

spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

BOARD = pcbnew.LoadBoard(rt.BOARD)
R = rt.Router(BOARD)
rt.absorb(BOARD, R)
print("frozen: %d tracks / %d vias\n" % (len(R.frozen), len(R.frozen_vias)))

AREA = rt.NX * rt.NY
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def flood(net, hw):
    """Set of flat node indices reachable from pads[0] of `net`."""
    bm, vm = R.blocked_for(net, hw)
    blk = bytearray(bm.reshape(-1).tobytes())
    vb = bytearray(vm.reshape(-1).tobytes())
    pads = R.pads[net]
    _, _, nodes, layers = pads[0]

    seen = bytearray(len(blk))
    q = deque()
    for l in (layers or (0, 1)):
        for (i, j) in nodes:
            k = l * AREA + i * rt.NY + j
            if not blk[k] and not seen[k]:
                seen[k] = 1
                q.append(k)
    while q:
        k = q.popleft()
        l, rem = divmod(k, AREA)
        i, j = divmod(rem, rt.NY)
        base = l * AREA
        for di, dj in DIRS:
            ni, nj = i + di, j + dj
            if ni < 0 or nj < 0 or ni >= rt.NX or nj >= rt.NY:
                continue
            nk = base + ni * rt.NY + nj
            if blk[nk] or seen[nk]:
                continue
            if di and dj and (blk[base + (i + di) * rt.NY + j]
                              or blk[base + i * rt.NY + (j + dj)]):
                continue                      # no corner cutting
            seen[nk] = 1
            q.append(nk)
        nb = (1 - l) * AREA + rem
        if (not blk[nb] and not seen[nb] and not vb[k] and not vb[nb]
                and R.via_ok(rt.mx(i), rt.my(j))):
            seen[nb] = 1
            q.append(nb)
    return seen


STRANDED = ["ROW10", "ROW16", "ROW18", "ROW19", "ROW20",
            "CSEL0", "CSEL1", "CSEL2", "CSEL3", "CSEL4",
            "CSEL5", "CSEL6", "CSEL7", "IO10", "IO12", "+3V3"]

for net in STRANDED:
    pads = R.pads.get(net, [])
    if len(pads) < 2:
        print("%-9s only %d pad(s)" % (net, len(pads)))
        continue
    w = rt.WIDTHS.get(net, rt.DEFAULT_W)
    seen = flood(net, w / 2.0)
    total = sum(seen)
    hit, miss = [], []
    for k, (px, py, nodes, layers) in enumerate(pads):
        if k == 0:
            continue
        ok = any(seen[l * AREA + i * rt.NY + j]
                 for l in (layers or (0, 1)) for (i, j) in nodes)
        (hit if ok else miss).append((px, py))
    print("%-9s w=%.2f  reached %7d node(s) of %d   pads %d/%d"
          % (net, w, total, len(seen), len(hit), len(hit) + len(miss)))
    for (px, py) in miss:
        print("             MISS (%.3f, %.3f)" % (px, py))
    sys.stdout.flush()
