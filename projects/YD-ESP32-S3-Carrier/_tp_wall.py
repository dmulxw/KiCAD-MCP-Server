"""Is there a WALL, or is the answer an artefact of how I asked?

_tp_comp.py says 16 of the 31 nets are reachable from no legal site -- and the
break is clean: ROW0..ROW10 all reach, ROW11..ROW20 none do.  A clean break in y
is what a horizontal wall looks like, and it is also what a bug in the seeding
rule looks like, so name it: print the bounding box of every component a site
can actually stand in.  If the reachable set has a ceiling, there is a wall
there and the pivot is dead on this board; if the reachable set spans the whole
board and the nets still do not connect, my model is wrong instead.
"""
import collections
import json
import sys

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
from probe import NGrid                                   # noqa: E402
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
HALO_BAND = KEEP + 2 * STEP

NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
LIB = "C:/Program Files/KiCad/10.0/share/footprints"
LIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty"
FP = "SOIC-16_3.9x9.9mm_P1.27mm"
OUT_PADS = ["15", "1", "2", "3", "4", "5", "6", "7"]

import os
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

# bbox per component, in mm (note the arrays are [j, i] = [y, x])
BB = {}
for lay in LAYERS:
    c = comp[lay]
    m = c >= 0
    if not m.any():
        continue
    j, i = np.nonzero(m)
    k = c[j, i]
    for a in np.unique(k).tolist():
        sel = k == a
        x0 = g.x0 + i[sel].min() * STEP
        x1 = g.x0 + i[sel].max() * STEP
        y0 = g.y0 + j[sel].min() * STEP
        y1 = g.y0 + j[sel].max() * STEP
        if a in BB:
            b = BB[a]
            BB[a] = (min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1))
        else:
            BB[a] = (x0, y0, x1, y1)

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
print("board: %s   sites: %d" % (BOARD, len(ALL)))
reach = collections.Counter()
for side, cx, cy in ALL:
    for k in seeds_from_pads(cx, cy):
        reach[k] += 1

print("components a site can stand in: %d" % len(reach))
tot = 0
for k, n in reach.most_common():
    b = BB[k]
    tot += size[k]
    print("   #%-4d %9d cells %8.1f mm2   sites %4d   x %.1f..%.1f  y %.1f..%.1f"
          % (k, size[k], size[k] * STEP * STEP, n, b[0], b[2], b[1], b[3]))
print("   total reachable: %d cells, %.1f mm2"
      % (tot, tot * STEP * STEP))

allb = (min(BB[k][0] for k in reach), min(BB[k][1] for k in reach),
        max(BB[k][2] for k in reach), max(BB[k][3] for k in reach))
print("   union bbox: x %.1f..%.1f  y %.1f..%.1f" % allb)

# ---- where is each net's copper, and is any of it inside the reachable bbox --
pts = collections.defaultdict(list)
for t in board.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    if n in NAMES:
        pts[n].append((s.x / S, s.y / S))
        pts[n].append((e.x / S, e.y / S))

print("\nnet copper extent (tracks only) vs the reachable window:")
for n in NAMES:
    a = np.array(pts.get(n, []))
    if len(a) == 0:
        print("   %-6s (no track copper)" % n)
        continue
    x0, y0 = a[:, 0].min(), a[:, 1].min()
    x1, y1 = a[:, 0].max(), a[:, 1].max()
    inside = (x1 >= allb[0] and x0 <= allb[2] and y1 >= allb[1] and y0 <= allb[3])
    print("   %-6s x %6.1f..%6.1f  y %6.1f..%6.1f   %s"
          % (n, x0, x1, y0, y1,
             "reaches into the window" if inside else "OUTSIDE the window"))
