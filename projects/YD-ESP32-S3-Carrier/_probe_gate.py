"""What is actually sealing the pads route.py cannot reach?

route_all() repairs stragglers by ripping up nets -- but it rips only
router.tracks (this pass's copper) and never router.frozen (the 1192 segments
HEAD already had).  So a failure blocked by pre-existing copper is one the
repair pass can never fix, no matter how many rounds it runs.  Which of the two
it is decides everything: frozen means the placement/plan is wrong and no router
setting will help, tracks means it is ordinary congestion.

Flood the legal mask for one net and name the net owning each frontier cell.

    python _probe_gate.py ROW5 CSEL0 +3V3
"""
import sys, os
from collections import Counter, deque

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import numpy as np
import pcbnew

import route as R

S = 1e6
NL = R.NL


def flood(router, m, v, starts):
    """Legal cells reachable from `starts`, with same-layer steps and vias.

    The via step must ask router.via_ok too.  Honouring only the copper mask lets
    this flood drop a via inside VIA_BAN -- the two "keep dead flat" boxes -- and
    report nets reachable that route_net() then refuses, which is precisely the
    wrong answer when the point of the probe is to tell congestion from geometry.
    """
    seen = set(starts)
    q = deque(starts)
    while q:
        l, i, j = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            i2, j2 = i + di, j + dj
            if not (0 <= i2 < R.NX and 0 <= j2 < R.NY):
                continue
            if (l, i2, j2) in seen or m[l, i2, j2]:
                continue
            seen.add((l, i2, j2))
            q.append((l, i2, j2))
        x, y = R.mx(i), R.my(j)
        if not router.via_ok(x, y):
            continue
        for l2 in range(NL):
            if l2 == l or (l2, i, j) in seen or v[l2, i, j]:
                continue
            seen.add((l2, i, j))
            q.append((l2, i, j))
    return seen


def main():
    board = pcbnew.LoadBoard(R.BOARD)
    router = R.Router(board)
    R.absorb(board, router)

    names = sorted({sh[0] for sh in router.shapes})
    frozen_nets = sorted({t[0] for t in router.frozen})

    for net in sys.argv[1:]:
        hw = R.WIDTHS.get(net, R.DEFAULT_W) / 2.0
        m, v = router.blocked_for(net, hw)
        pads = router.pads.get(net, [])
        if len(pads) < 2:
            print("%s: %d pad(s) -- nothing to route" % (net, len(pads)), flush=True)
            continue
        # flood from the first pad, see which others it can reach
        starts = []
        for (i, j) in pads[0][2]:
            for l in (pads[0][3] or (0, 1)):
                if not m[l, i, j]:
                    starts.append((l, i, j))
        seen = flood(router, m, v, starts)
        got = []
        for n, (px, py, nodes, layers) in enumerate(pads[1:], 1):
            if any((l, i, j) in seen for (i, j) in nodes for l in (layers or (0, 1))):
                got.append(n)

        xs = [i for _, i, _ in seen]
        ys = [j for _, _, j in seen]
        print("\n%s  hw=%.2f  pads=%d  reach %d cells  x %.1f..%.1f  y %.1f..%.1f"
              % (net, hw, len(pads), len(seen), min(xs) * R.GRID, max(xs) * R.GRID,
                 min(ys) * R.GRID, max(ys) * R.GRID), flush=True)
        print("   reached %d/%d other pads" % (len(got), len(pads) - 1), flush=True)
        for n, (px, py, _nodes, _layers) in enumerate(pads, 0):
            if n and n not in got:
                print("   unreached pad %d @(%.2f,%.2f)" % (n, px, py), flush=True)

        # who owns the cells just outside the reachable set
        wall = Counter()
        for (l, i, j) in seen:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                i2, j2 = i + di, j + dj
                if not (0 <= i2 < R.NX and 0 <= j2 < R.NY):
                    continue
                if (l, i2, j2) in seen or not m[l, i2, j2]:
                    continue
                wall[("blocked",)] += 1
        print("   frontier cells: %d" % wall[("blocked",)], flush=True)

        # attribute the frontier: re-block one candidate net at a time and count
        # how many frontier cells it owns alone.  Cheap enough: a full pass per net.
        frontier = set()
        for (l, i, j) in seen:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                i2, j2 = i + di, j + dj
                if 0 <= i2 < R.NX and 0 <= j2 < R.NY and (l, i2, j2) not in seen:
                    frontier.add((l, i2, j2))
        fa = np.zeros((NL, R.NX, R.NY), dtype=bool)
        for (l, i, j) in frontier:
            fa[l, i, j] = True

        own = Counter()
        for other in names:
            if other == net:
                continue
            om, _ov = router.blocked_for(other, hw)
            own[other] += int((om & fa & m).sum())
        # copper already on the board, which the repair pass cannot lift
        fz = Counter()
        for (onet, layer, x1, y1, x2, y2, w) in router.frozen:
            if onet == net:
                continue
            z = np.zeros((NL, R.NX, R.NY), dtype=bool)
            R.raster_seg(z, layer, x1, y1, x2, y2, w / 2.0 + R.CLEAR + hw)
            fz[onet] += int((z & fa).sum())

        print("   by net:  " + ", ".join("%s x%d" % (n, c)
                                          for n, c in own.most_common(8) if c), flush=True)
        print("   FROZEN:  " + ", ".join("%s x%d" % (n, c)
                                          for n, c in fz.most_common(8) if c), flush=True)


if __name__ == "__main__":
    main()
