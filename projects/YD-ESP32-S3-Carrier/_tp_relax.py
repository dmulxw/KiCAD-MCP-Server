"""How far is each net's copper from free space a chip can stand in?

_tp_comp.py's net_comp rule is `own == n`, i.e. only cells for which net n is
the NEAREST copper owner count as "touching n".  That is conservative: a legal
cell 0.40mm from ROW11's trunk but 0.35mm from foreign copper is a perfectly good
landing pad for a route, yet it is attributed to the foreign net and ROW11 looks
unreachable.  The conservative rule can only UNDER-count, so it cannot be trusted
for a negative verdict on its own.

So measure the thing directly and without an ownership rule: take the free space
a site can stand in (the components _tp_wall.py found), distance-transform it,
and read the distance at each net's own copper.  That gap is the copper a route
would have to cross -- if it is small, the "0 sites" verdict was an artefact of
how I asked; if it is millimetres, there is a real wall and the pivot is dead.
"""
import collections
import json
import sys

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
from probe import NGrid, octile_dt                        # noqa: E402
from _tp_label import label_free                          # noqa: E402

S = 1e6
F_Cu, B_Cu = pcbnew.F_Cu, pcbnew.B_Cu
LAYERS = [F_Cu, B_Cu]

STEP = 0.1
CLEAR, SAFETY = 0.20, 0.04
KEEP = CLEAR + 0.1 + SAFETY
PAD_KEEP = CLEAR + 0.3 + SAFETY
EGK = 0.50 + CLEAR + SAFETY
VEK = EGK + 0.3

NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
LIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty"
FP = "SOIC-16_3.9x9.9mm_P1.27mm"
OUT_PADS = ["15", "1", "2", "3", "4", "5", "6", "7"]

import os                                                  # noqa: E402
BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")
SITES_IN = os.environ.get("TP_SITES_OUT", "_tp_places.json")
board = pcbnew.LoadBoard(BOARD)
g = NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
items = list(board.GetTracks())
for fp in board.GetFootprints():
    items.extend(fp.Pads())
g.build(items)

comp, K = label_free(g.OK, g.VOK, LAYERS, g.nx, g.ny, quiet=True)
size = np.bincount(np.concatenate([comp[l][comp[l] >= 0] for l in LAYERS]),
                   minlength=K)

# ---- the free space a site can stand in ------------------------------------
fp0 = pcbnew.FootprintLoad(LIB, FP)
PADOFF = {}
for p in fp0.Pads():
    n = p.GetNumber()
    if n in OUT_PADS:
        c = p.GetPosition()
        PADOFF[n] = (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))


def seeds_from_pads(cx, cy, r=1.0):
    got = set()
    for n in OUT_PADS:
        dx, dy = PADOFF[n]
        px, py = cx + dx, cy + dy
        i0 = max(0, int((px - r - g.x0) / STEP))
        i1 = min(g.nx - 1, int((px + r - g.x0) / STEP))
        j0 = max(0, int((py - r - g.y0) / STEP))
        j1 = min(g.ny - 1, int((py + r - g.y0) / STEP))
        if i1 < i0 or j1 < j0:
            continue
        xs = g.x0 + np.arange(i0, i1 + 1) * STEP
        ys = g.y0 + np.arange(j0, j1 + 1) * STEP
        near = np.hypot(xs[None, :] - px, ys[:, None] - py) <= r
        m = near & g.OK[F_Cu][j0:j1 + 1, i0:i1 + 1]
        if m.any():
            got.update(np.unique(comp[F_Cu][j0:j1 + 1, i0:i1 + 1][m]).tolist())
    got.discard(-1)
    return got


ALL = json.load(open(SITES_IN))["all_sites"]
print("board: %s   sites: %s (%d)" % (BOARD, SITES_IN, len(ALL)))
reach = collections.Counter()
for side, cx, cy in ALL:
    for k in seeds_from_pads(cx, cy):
        reach[k] += 1
print("components a site can stand in: %s"
      % ", ".join("#%d (%d sites, %d cells)" % (k, n, size[k])
                  for k, n in reach.most_common()))

# ---- distance from anywhere to that free space, on ONE plane ---------------
# Both layers go into one mask: a copper cell on B.Cu measuring its distance to a
# reachable cell on F.Cu is optimistic (it would really need a via), and
# optimistic is what a negative verdict needs -- if even this says the gap is
# wide, the wall is real.
SITE_CELLS = np.zeros((g.ny, g.nx), bool)
for k in reach:
    for lay in LAYERS:
        SITE_CELLS |= (comp[lay] == k)
dt = octile_dt(SITE_CELLS, STEP) * STEP                   # mm to nearest site cell
print("site-reachable free space: %d cells (union of layers), %.1f mm2"
      % (int(SITE_CELLS.sum()), SITE_CELLS.sum() * STEP * STEP))

# ---- each net's own copper, as points --------------------------------------
pts = collections.defaultdict(list)
for t in board.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    if n not in NAMES:
        continue
    x0, y0, x1, y1 = s.x / S, s.y / S, e.x / S, e.y / S
    k = max(2, int(np.hypot(x1 - x0, y1 - y0) / 0.5) + 1)
    for q in range(k + 1):
        f = q / k
        pts[n].append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
for fp in board.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if n in NAMES:
            q = p.GetPosition()
            pts[n].append((q.x / S, q.y / S))

print("\ngap from each net's own copper to reachable free space:")
print("  %-6s %8s   %s" % ("net", "gap mm", "where (mm)"))
rows = []
for n in NAMES:
    a = np.array(pts.get(n, []))
    if len(a) == 0:
        rows.append((999.0, n, ""))
        continue
    bi = np.clip(((a[:, 0] - g.x0) / STEP).round().astype(int), 0, g.nx - 1)
    bj = np.clip(((a[:, 1] - g.y0) / STEP).round().astype(int), 0, g.ny - 1)
    d = dt[bj, bi]
    q = int(np.argmin(d))
    rows.append((float(d[q]), n, "(%.1f, %.1f)" % (a[q, 0], a[q, 1]), a[q]))
for d, n, w, _ in sorted(rows):
    print("  %-6s %8.2f   %s" % (n, d, w))

print("\nnet copper within one grid step (<= %.2f mm) of reachable free space:"
      % (STEP * 1.5))
ok = [n for d, n, _, _ in rows if d <= STEP * 1.5]
print("   %d/%d: %s" % (len(ok), len(NAMES), " ".join(sorted(ok))))


# ---- what is IN the gap -----------------------------------------------------
# A gap is only fatal if the copper in it cannot move.  This board already has a
# precedent: ROW3/ROW5 were solved by deleting ONE GND link (30 segments,
# x 100.30-102.40 y 118.91-146.92) and re-bridging the six islands it left.  So
# name the blockers: if they are GND, the same surgery may open these too; if
# they are other ROW/CSEL copper, nothing can be moved and the verdict is final.
net_of = np.array([it.GetNetname() for it in items], dtype=object)

print("\nwhat blocks each unreached net (copper within gap + 0.3mm of the")
print("closest approach point, by owning net):")
for d, n, w, P in sorted(rows):
    if d <= STEP * 1.5:
        continue
    R = d + 0.3
    i0 = max(0, int((P[0] - R - g.x0) / STEP))
    i1 = min(g.nx - 1, int((P[0] + R - g.x0) / STEP))
    j0 = max(0, int((P[1] - R - g.y0) / STEP))
    j1 = min(g.ny - 1, int((P[1] + R - g.y0) / STEP))
    if i1 < i0 or j1 < j0:
        continue
    tally = collections.Counter()
    for lay in LAYERS:
        o = g.OWN[lay][j0:j1 + 1, i0:i1 + 1]
        free = comp[lay][j0:j1 + 1, i0:i1 + 1] >= 0
        m = (o >= 0) & ~free
        if m.any():
            idx = o[m]
            for nm, c in zip(*np.unique(net_of[idx], return_counts=True)):
                tally[str(nm)] += int(c)
    top = ", ".join("%s x%d" % (nm, c) for nm, c in tally.most_common(5))
    print("  %-6s gap %5.2f at %s   %s" % (n, d, w, top or "(nothing -- free space)"))
