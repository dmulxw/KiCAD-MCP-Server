"""On the untouched board, is each panel net's start pad connected to its
destination pad at all?

route_all() reports only *that* a net failed.  Failure comes in two flavours and
they need opposite fixes:

  * UNREACHABLE -- flood-fill from the net's own pad does not contain the other
    pad, on any legal layer or via.  Nothing about ordering can help; the strip's
    geometry has to change.
  * CONTENTION -- every net is reachable on its own, so the failure is the order
    the nets were laid in, and route_all()'s rip-up is what has to get better.

This runs on the restored board, before any new copper exists, so a failure here
is structural and not caused by an earlier net.

Reported per net: pad count reached, the size of the reached region (a small
region means a sealed pocket -- the part has to move; a huge one means the
approach is walled off -- a corridor is missing), and the coordinates of the
pads that were not reached.
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


def flood_from(net, hw, start):
    """Set of flat nodes reachable from node-group `start` under the mask."""
    bm, vm = R.blocked_for(net, hw)
    blk = bytearray(bm.reshape(-1).tobytes())
    vb = bytearray(vm.reshape(-1).tobytes())
    _, _, nodes, layers = start

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


bad = 0
for net in rt.ONLY:
    pads = R.pads.get(net, [])
    if len(pads) < 2:
        print("%-10s only %d pad(s)" % (net, len(pads)))
        continue
    w = rt.WIDTHS.get(net, rt.DEFAULT_W)
    seen = flood_from(net, w / 2.0, pads[0])

    hit, miss = [pads[0][:2]], []
    for p in pads[1:]:
        px, py, nodes, layers = p
        ok = any(seen[l * AREA + i * rt.NY + j]
                 for l in (layers or (0, 1)) for (i, j) in nodes)
        (hit if ok else miss).append((px, py))

    if not miss:
        print("%-10s OK        all %d pad(s) in one region of %d node(s)"
              % (net, len(pads), sum(seen)))
        continue

    bad += 1
    print("%-10s UNREACH  %d/%d pad(s); region %d node(s)"
          % (net, len(hit), len(pads), sum(seen)))
    for (px, py) in miss:
        # How big is the pocket the stranded pad sits in?
        pocket = flood_from(net, w / 2.0, (px, py, [(rt.gi(px), rt.gj(py))], None))
        print("             MISS (%7.3f, %7.3f)   pocket %d node(s)"
              % (px, py, sum(pocket)))
    sys.stdout.flush()

print("\n%d of %d net(s) unreachable on the bare board" % (bad, len(rt.ONLY)))
