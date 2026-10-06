"""Which existing pads can a chip actually land on?

Option B needs four things to reach the chips: the 12 driven nets (measured
reachable), plus SER/SRCLK/RCLK/~OE and +3V3/GND, which have to arrive from the
cable somewhere.  Every pad on the board is a candidate landing point, so measure
the same gap _tp_relax.py measured for nets -- distance from the pad to the free
space a chip can stand in.  If the header spare pads are walled off like the 19
nets were, the control lines cannot come from the headers, and that is a fact
worth having before anything is placed rather than after.
"""
import collections
import json
import os
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

LIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty"
FP = "SOIC-16_3.9x9.9mm_P1.27mm"
OUT_PADS = ["15", "1", "2", "3", "4", "5", "6", "7"]

BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")
SITES_IN = os.environ.get("TP_SITES_OUT", "_tp_places_orig.json")
board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard(%s) returned None" % BOARD)
g = NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
items = list(board.GetTracks())
for fp in board.GetFootprints():
    items.extend(fp.Pads())
g.build(items)

comp, K = label_free(g.OK, g.VOK, LAYERS, g.nx, g.ny, quiet=True)

fp0 = pcbnew.FootprintLoad(LIB, FP)
PADOFF = {}
for p in fp0.Pads():
    if p.GetNumber() in OUT_PADS:
        c = p.GetPosition()
        PADOFF[p.GetNumber()] = (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))


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
reach = collections.Counter()
for side, cx, cy in ALL:
    for k in seeds_from_pads(cx, cy):
        reach[k] += 1
print("board: %s   sites: %d" % (BOARD, len(ALL)))
print("components a site can stand in: %s"
      % ", ".join("#%d (%d sites)" % (k, n) for k, n in reach.most_common()))

SITE_CELLS = np.zeros((g.ny, g.nx), bool)
for k in reach:
    for lay in LAYERS:
        SITE_CELLS |= (comp[lay] == k)
dt = octile_dt(SITE_CELLS, STEP) * STEP
print("site-reachable free space: %d cells on one plane, %.1f mm2\n"
      % (int(SITE_CELLS.sum()), SITE_CELLS.sum() * STEP * STEP))


def gap_at(x, y):
    i = int(np.clip(round((x - g.x0) / STEP), 0, g.nx - 1))
    j = int(np.clip(round((y - g.y0) / STEP), 0, g.ny - 1))
    return float(dt[j, i])


rows = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith("Q") or ref.startswith("R"):
        continue                       # 220 AO3400 + 31 pull resistors: skip
    for p in fp.Pads():
        c = p.GetPosition()
        x, y = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
        w = pcbnew.ToMM(p.GetSizeX()) / 2
        h = pcbnew.ToMM(p.GetSizeY()) / 2
        d = min(gap_at(x, y), gap_at(x + w, y), gap_at(x - w, y),
                gap_at(x, y + h), gap_at(x, y - h))
        rows.append((d, ref, p.GetNumber(), x, y, p.GetNetname() or "--"))

rows.sort()
print("every non-Q/non-R pad, nearest to reachable free space first:")
print("  %-5s %-4s %8s  %-22s  %s" % ("ref", "pad", "gap mm", "at (mm)", "net"))
for d, ref, num, x, y, net in rows:
    print("  %-5s %-4s %8.2f  (%8.2f, %8.2f)  %s" % (ref, num, d, x, y, net))
