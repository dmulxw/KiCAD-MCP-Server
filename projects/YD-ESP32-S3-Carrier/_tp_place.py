"""Choose the four 595 sites by exact assignment, not by greedy.

_tp_assign.py's greedy filled the bottom-right chip with eight 7 mm nets and then
had to dump CSEL7/8/9 on a chip 76 mm away, because greedy has no way to give up a
cheap net to make room for a dear one.  With eight slots per chip that is exactly
the decision that matters, so solve it properly: minimum-cost flow, 31 nets into 4
chips of capacity 8.  Bellman-Ford over 37 nodes, 31 augmentations -- instant.

Site positions are then refined against that solver: hold three sites, scan the
fourth over every legal position in its margin, keep whichever gives the cheapest
exact assignment.  Repeat until nothing moves.

Two things are read off the board rather than assumed:

  * footprint courtyards -- a site the scan returns is one a chip fits on;
  * F.Cu copper.  An SOIC-16 is surface-mount, so only its two 1.95 x 9.5 pad
    strips touch the top layer; the 3.0 mm spine between them does not.  Testing
    the strips instead of the whole courtyard lets a chip straddle existing
    tracks, which matters a lot in a margin that already carries 1080 mm of them.
"""
import collections
import itertools
import json
import sys

import numpy as np
import pcbnew

STEP = 0.25
CY_HW, CY_HH = 3.7, 5.2               # courtyard half-extents, rot 0
PAD_X, PAD_Y = 2.475, 4.745           # pad-strip centre x, half-height
PAD_HW, PAD_HH = 0.975, 0.3           # pad half-size, from (size 1.95 0.6)
COPPER_KEEP = 0.20                    # site pad strip -> foreign F.Cu
CAP = 8
BIG = 1e6

import os
BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")
SITES_OUT = os.environ.get("TP_SITES_OUT", "_tp_places.json")
b = pcbnew.LoadBoard(BOARD)
S = 1e6
NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]

# ---- net copper, sampled every 0.5 mm -------------------------------------
pts = collections.defaultdict(list)
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    if not n:
        continue
    x0, y0, x1, y1 = s.x / S, s.y / S, e.x / S, e.y / S
    k = max(2, int((((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5) / 0.5) + 1)
    for q in range(k + 1):
        f = q / k
        pts[n].append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
for fp in b.GetFootprints():
    for p in fp.Pads():
        q = p.GetPosition()
        pts[p.GetNetname()].append((q.x / S, q.y / S))
NET = {n: np.array(pts[n]) for n in NAMES if pts.get(n)}

# ---- board outline ---------------------------------------------------------
xs, ys = [], []
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        for p in (d.GetStart(), d.GetEnd()):
            xs.append(pcbnew.ToMM(p.x)); ys.append(pcbnew.ToMM(p.y))
X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
NX = int((X1 - X0) / STEP) + 2
NY = int((Y1 - Y0) / STEP) + 2


def blank():
    return np.zeros((NX, NY), dtype=bool)


def span(a, lo):                       # mm -> inclusive grid index span
    return int((a - lo) / STEP + 0.5)


# ---- occupancy: any footprint's courtyard ---------------------------------
# ...and, separately, F.Cu copper, which only the pad strips care about.
cy_occ = blank()
cu_occ = blank()
for fp in b.GetFootprints():
    bb = fp.GetBoundingBox(False, False)
    i0 = max(0, span(pcbnew.ToMM(bb.GetLeft()), X0))
    i1 = min(NX - 1, span(pcbnew.ToMM(bb.GetRight()), X0))
    j0 = max(0, span(pcbnew.ToMM(bb.GetTop()), Y0))
    j1 = min(NY - 1, span(pcbnew.ToMM(bb.GetBottom()), Y0))
    if i1 >= i0 and j1 >= j0:
        cy_occ[i0:i1 + 1, j0:j1 + 1] = True
    for p in fp.Pads():
        if not (p.GetLayerSet().Contains(pcbnew.F_Cu)):
            continue
        pb = p.GetBoundingBox()
        a0 = max(0, span(pcbnew.ToMM(pb.GetLeft()) - COPPER_KEEP, X0))
        a1 = min(NX - 1, span(pcbnew.ToMM(pb.GetRight()) + COPPER_KEEP, X0))
        b0 = max(0, span(pcbnew.ToMM(pb.GetTop()) - COPPER_KEEP, Y0))
        b1 = min(NY - 1, span(pcbnew.ToMM(pb.GetBottom()) + COPPER_KEEP, Y0))
        if a1 >= a0 and b1 >= b0:
            cu_occ[a0:a1 + 1, b0:b1 + 1] = True
for t in b.GetTracks():
    if t.GetLayer() != pcbnew.F_Cu:
        continue
    for p in (t.GetStart(), t.GetEnd()):
        pass
    s, e = t.GetStart(), t.GetEnd()
    x0, y0 = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
    x1, y1 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
    w = t.GetWidth() / float(S) / 2.0 + COPPER_KEEP
    n = max(2, int(np.hypot(x1 - x0, y1 - y0) / (STEP / 2.0)) + 1)
    for q in range(n + 1):
        f = q / n
        cx, cy = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        i0 = max(0, span(cx - w, X0)); i1 = min(NX - 1, span(cx + w, X0))
        j0 = max(0, span(cy - w, Y0)); j1 = min(NY - 1, span(cy + w, Y0))
        if i1 >= i0 and j1 >= j0:
            cu_occ[i0:i1 + 1, j0:j1 + 1] = True


def box_free(occ, cx, cy, hw, hh, margin=0.0):
    hw += margin; hh += margin
    i0 = span(cx - hw, X0) + 1
    i1 = span(cx + hw, X0) - 1
    j0 = span(cy - hh, Y0) + 1
    j1 = span(cy + hh, Y0) - 1
    if i0 > i1 or j0 > j1 or i0 < 0 or j0 < 0 or i1 >= NX or j1 >= NY:
        return False
    return not occ[i0:i1 + 1, j0:j1 + 1].any()


def fits(cx, cy):
    """Courtyard clear of footprints, both pad strips clear of F.Cu copper."""
    if not box_free(cy_occ, cx, cy, CY_HW, CY_HH):
        return False
    for sx in (-PAD_X, PAD_X):
        if not box_free(cu_occ, cx + sx, cy, PAD_HW, PAD_Y + PAD_HH, 0.05):
            return False
    return True


# Margins first: x < 104.2 or x > 166.8, chip body inside the outline.  With
# --all, sweep the interior too -- the electrode array is B.Cu only, so an
# SOIC-16's F.Cu pad strips have nothing to clear there, and if an interior site
# exists it seeds a different set of free-space components than the margins do.
# Assume nothing about that; test it.
def rng(a, b, s=0.5):
    return np.arange(np.ceil(a / s - 1e-9) * s, b + 1e-9, s)


GX = [("L", rng(X0 + 0.5 + CY_HW, 100.5), 104.2),
      ("R", rng(170.5, X1 - 0.5 - CY_HW), 166.8)]
if "--all" in sys.argv:
    GX.append(("I", np.arange(104.0, 167.5, 0.5), None))

SITES = []
for side, xg, lim in GX:
    for cx in xg:
        cx = float(cx)
        if cx - CY_HW < X0 + 0.5 or cx + CY_HW > X1 - 0.5:
            continue
        if lim is not None and side == "L" and cx + CY_HW > lim:
            continue
        if lim is not None and side == "R" and cx - CY_HW < lim:
            continue
        for cy10 in range(int((Y0 + 5.2) * 10), int((Y1 - 5.2) * 10) + 1, 10):
            cy = cy10 / 10.0
            if fits(cx, cy):
                SITES.append((side, cx, cy))
print("legal rot-0 SOIC-16 sites (courtyard + F.Cu pad strips): %d"
      % len(SITES))
_by = collections.Counter(s[0] for s in SITES)
print("   left %d, right %d, interior %d   (%s columns screened)"
      % (_by["L"], _by["R"], _by["I"],
         " + ".join("%d %s" % (len(g[1]), g[0]) for g in GX)))
if _by["I"] == 0 and any(g[0] == "I" for g in GX):
    print("   interior is not merely tight -- ZERO of the %d interior columns"
          % len(GX[-1][1]))
    print("   admit an SOIC-16 courtyard, so the margins are the only ground")

# The seed search below is ~8M greedy calls and it answers "which four sites",
# which is a different question from "can any four sites reach all 31 nets".
# That second question is placement-independent and needs only the list, so
# let it have one without paying for the first.
if "--sites" in sys.argv:
    json.dump({"all_sites": [[s[0], s[1], s[2]] for s in SITES]},
              open(SITES_OUT, "w"))
    print("wrote %s (%d sites)" % (SITES_OUT, len(SITES)))
    raise SystemExit(0)

D = np.full((len(NAMES), len(SITES)), BIG)
for r, n in enumerate(NAMES):
    a = NET.get(n)
    if a is None:
        continue
    for c, (_, cx, cy) in enumerate(SITES):
        D[r, c] = float(np.min(np.hypot(a[:, 0] - cx, a[:, 1] - cy)))

LEFT = [c for c, s in enumerate(SITES) if s[0] == "L"]
RIGHT = [c for c, s in enumerate(SITES) if s[0] == "R"]


def assign(cols):
    """Exact min-cost 31-nets-into-4-chips-of-8, by successive shortest paths."""
    m = len(cols)
    N = 1 + len(NAMES) + m + 1
    src, snk = 0, N - 1
    head = [[] for _ in range(N)]
    to, cap, cost, rev = [], [], [], []

    def edge(u, v, c, w):
        to.append(v); cap.append(c); cost.append(w); rev.append(len(to))
        to.append(u); cap.append(0); cost.append(-w); rev.append(len(to) - 2)
        head[u].append(len(to) - 2)
        head[v].append(len(to) - 1)

    for r in range(len(NAMES)):
        edge(src, 1 + r, 1, 0.0)
        for k, c in enumerate(cols):
            if D[r, c] < BIG:
                edge(1 + r, 1 + len(NAMES) + k, 1, D[r, c])
    for k in range(m):
        edge(1 + len(NAMES) + k, snk, CAP, 0.0)

    total, n_flow = 0.0, 0
    while n_flow < len(NAMES):
        dist = [BIG] * N
        dist[src] = 0.0
        pe = [-1] * N
        for _ in range(N):
            upd = False
            for u in range(N):
                if dist[u] >= BIG:
                    continue
                for e in head[u]:
                    v = to[e]
                    if cap[e] > 0 and dist[u] + cost[e] < dist[v] - 1e-9:
                        dist[v] = dist[u] + cost[e]
                        pe[v] = e
                        upd = True
            if not upd:
                break
        if dist[snk] >= BIG:
            break
        v = snk
        while v != src:
            e = pe[v]
            cap[e] -= 1
            cap[rev[e]] += 1
            v = to[rev[e]]
        total += dist[snk]
        n_flow += 1
    return total if n_flow == len(NAMES) else None


def solve(sites):
    try:
        cols = [SITES.index(s) for s in sites]
    except ValueError:
        return None
    return assign(cols)


def greedy_cols(cols):
    pairs = sorted(((D[r, c], r, c) for r in range(len(NAMES)) for c in cols))
    used = collections.Counter()
    got = {}
    for d, r, c in pairs:
        if r in got or used[c] >= CAP:
            continue
        got[r] = (c, d)
        used[c] += 1
    return got if len(got) == len(NAMES) else None


def lower_bound(cols):
    """Cheapest each net could possibly be, ignoring the 8-per-chip capacity.

    Four chips x 8 outputs = 32 slots for 31 nets, so capacity is almost exactly
    tight: at most ONE net can be displaced from its favourite chip.  That makes
    this bound nearly exact, which is what lets it screen candidates -- a position
    whose bound is already worse than a known exact cost cannot be an improvement.
    """
    return float(D[:, cols].min(axis=1).sum())


# Start from the best greedy combo over a coarse subsample of each pool; the
# coordinate-descent below is what actually places the chips, so a rough seed is
# enough and the exhaustive pair search is not worth its runtime.
best = None
for lp in itertools.combinations(LEFT[::3], 2):
    for rp in itertools.combinations(RIGHT[::3], 2):
        g = greedy_cols(list(lp) + list(rp))
        if g is None:
            continue
        t = sum(d for _, d in g.values())
        if best is None or t < best[0]:
            best = (t, lp, rp)
if best is None:
    raise SystemExit("no pair of left/right sites can hold all 31 nets")
print("greedy start (%.0f): %s + %s"
      % (best[0], [SITES[c] for c in best[1]], [SITES[c] for c in best[2]]))

sites = [SITES[c] for c in list(best[1]) + list(best[2])]
cur = solve(sites)
if cur is None:
    raise SystemExit("seed sites cannot hold all 31 nets")
for it in range(6):
    moved = False
    for k in range(4):
        pool = [SITES[c] for c in (LEFT if sites[k][0] == "L" else RIGHT)]
        cur = solve(sites)
        bestp, bestt = sites[k], cur
        for p in pool:
            if p in sites:
                continue
            trial = list(sites)
            trial[k] = p
            if lower_bound([SITES.index(t) for t in trial]) > bestt - 1e-6:
                continue                      # cannot beat the incumbent
            t = solve(trial)
            if t is not None and t < bestt - 1e-6:
                bestt, bestp = t, p
        if bestp != sites[k]:
            sites[k] = bestp
            moved = True
    print("  pass %d: %s  cost %.0f"
          % (it + 1, ["%s(%.1f,%.1f)" % s for s in sites], solve(sites) or -1))
    if not moved:
        print("  converged")
        break

print("\nchosen sites:")
for k, s in enumerate(sites):
    print("   chip %s  %s x=%.1f y=%.1f" % ("ABCD"[k], s[0], s[1], s[2]))

cols = [SITES.index(s) for s in sites]

# Recover the exact assignment from the flow solution by re-running it and
# reading which net->site arcs carry flow.
m = len(cols)
N = 1 + len(NAMES) + m + 1
src, snk = 0, N - 1
head = [[] for _ in range(N)]
to, cap, cost, rev = [], [], [], []


def edge(u, v, c, w):
    to.append(v); cap.append(c); cost.append(w); rev.append(len(to))
    to.append(u); cap.append(0); cost.append(-w); rev.append(len(to) - 2)
    head[u].append(len(to) - 2)
    head[v].append(len(to) - 1)


for r in range(len(NAMES)):
    edge(src, 1 + r, 1, 0.0)
    for k, c in enumerate(cols):
        edge(1 + r, 1 + len(NAMES) + k, 1, D[r, c])
for k in range(m):
    edge(1 + len(NAMES) + k, snk, CAP, 0.0)
n_flow = 0
while n_flow < len(NAMES):
    dist = [BIG] * N
    dist[src] = 0.0
    pe = [-1] * N
    for _ in range(N):
        upd = False
        for u in range(N):
            if dist[u] >= BIG:
                continue
            for e in head[u]:
                v = to[e]
                if cap[e] > 0 and dist[u] + cost[e] < dist[v] - 1e-9:
                    dist[v] = dist[u] + cost[e]
                    pe[v] = e
                    upd = True
        if not upd:
            break
    v = snk
    while v != src:
        e = pe[v]
        cap[e] -= 1
        cap[rev[e]] += 1
        v = to[rev[e]]
    n_flow += 1

by = collections.defaultdict(list)
for r in range(len(NAMES)):
    for k in range(m):
        e = next(i for i in head[1 + r] if to[i] == 1 + len(NAMES) + k)
        if cap[e] == 0:                       # arc used
            by[k].append((NAMES[r], D[r, cols[k]]))

print("\nexact assignment (cost %.0f, %d nets):" % (solve(sites), len(NAMES)))
for k, s in enumerate(sites):
    nets = sorted(by.get(k, []), key=lambda t: t[1])
    print("  chip %s (%s, %.1f)  %d nets  worst %5.1f mm\n      %s"
          % ("ABCD"[k], s[0], s[2], len(nets),
             max((d for _, d in nets), default=0),
             " ".join("%s(%.0f)" % t for t in nets)))

json.dump({"sites": [{"side": s[0], "x": s[1], "y": s[2]} for s in sites],
           "assign": {"ABCD"[k]: [n for n, _ in sorted(by.get(k, []),
                                                    key=lambda t: t[1])]
                      for k in range(4)},
           # Every legal site, not just the four chosen: the coverage question
           # ("can ANY four of them reach all 31 nets?") is placement-independent
           # and needs the whole list, not the answer to a different question.
           "all_sites": [[s[0], s[1], s[2]] for s in SITES]},
          open("_tp_place.json", "w"), indent=1)
print("\nwrote _tp_place.json (%d sites)" % len(SITES))
