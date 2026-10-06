"""Which nets can a chip reach from the strip below the array, or from the margins?

_tp_drive.py answered this one chip position at a time, and the two positions it
answered disagree by a factor of two: 12/31 beside J1A (rot 180, x 95.5) against
20/31 in the strip below the array (rot 0, x 135.5).  A sample is not a bound.
What the placement decision needs is the union over everywhere a chip could
stand: a net in neither the strip nor the margins can never be driven, no matter
how the four chips are arranged, and a net in both is slack the packer can use.

The measure is the clearance-gap proxy, which the real A* runs have already
calibrated on this board.  A gap of a few tenths of a millimetre means a legal
cell sits beside the copper and the last step onto your own net is legal by
definition; the nets that A* exhausted the entire board on reported gaps of many
millimetres.  So a small gap is a candidate and a large one is a rejection --
and every candidate is confirmed by A* before anything is placed.  This file is
a screening pass, not a verdict.
"""
import os
import sys
import time

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
import replan                                              # noqa: E402
import probe                                               # noqa: E402

S = 1e6
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
STEP = 0.1
CLEAR, SAFETY = 0.20, 0.04
KEEP = CLEAR + 0.1 + SAFETY
PAD_KEEP = CLEAR + 0.3 + SAFETY
EGK = 0.50 + CLEAR + SAFETY
VEK = EGK + 0.3

SIG = ["ROW%d" % k for k in range(21)] + ["CSEL%d" % k for k in range(10)]

EXT = float(os.environ.get("TP_EXTEND_DOWN", "0"))
DROP_J1 = bool(os.environ.get("TP_DROP_J1"))
BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard(%s) returned None" % BOARD)

keep_alive = []
if DROP_J1:
    gone = [f for f in board.GetFootprints() if f.GetReference() == "J1"]
    for f in gone:
        board.Remove(f)
    keep_alive.extend(gone)
    print("dropped %d footprint(s): J1" % len(gone))

if EXT:
    ys = [pt.y for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts
          for pt in (d.GetStart(), d.GetEnd())]
    YMAX = max(ys)
    n = 0
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        a, b2 = d.GetStart(), d.GetEnd()
        if abs(a.y - b2.y) < 1:
            continue
        hit = False
        for pt in (a, b2):
            if abs(pt.y - YMAX) < 1:
                pt.y = int(round(pt.y + EXT * S))
                hit = True
        if hit:
            d.SetStart(a)
            d.SetEnd(b2)
            n += 1
    print("extended bottom edge by %.0fmm (%d vertical edges)" % (EXT, n))

edges = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
exs, eys = [], []
for d in edges:
    for p in (d.GetStart(), d.GetEnd()):
        exs.append(pcbnew.ToMM(p.x))
        eys.append(pcbnew.ToMM(p.y))
print("outline: x %.2f..%.2f  y %.2f..%.2f" % (min(exs), max(exs),
                                               min(eys), max(eys)))

tracks = list(board.GetTracks())
pads = [p for f in board.GetFootprints() for p in f.Pads()]
print("board items: %d tracks, %d pads" % (len(tracks), len(pads)))

# The electrode array's copper ends at y = 241.5.  A chip is 10.4mm tall, so a
# centre below 244.0 leaves its whole body clear of the array and its output row
# inside the strip.  The top of the allowed band is deliberately generous: this
# is a screening pass and the packer applies the real courtyard rule.
Y_STRIP = 244.0
Y_MARGIN_LO, Y_MARGIN_HI = 100.0, 250.0
XMARGIN = 98.0
XARR_HI = 169.0


def sites(kind):
    """Legal standing cells for a chip in the strip, or in either margin."""
    xs = g.x0 + np.arange(g.nx) * STEP
    ys = g.y0 + np.arange(g.ny) * STEP
    Y = ys[:, None]
    X = xs[None, :]
    if kind == "strip":
        box = (Y >= Y_STRIP) & (Y <= max(eys) - 1.0)
    else:
        box = (X <= XMARGIN) | (X >= XARR_HI)
        box = box & (Y >= Y_MARGIN_LO) & (Y <= Y_MARGIN_HI)
    box = np.broadcast_to(box, (g.ny, g.nx))
    m = np.zeros((g.ny, g.nx), bool)
    for lay in LAYERS:
        m |= g.OK[lay] & box
    return m


print("\n%-6s %9s %-18s %9s %-18s %s"
      % ("net", "gap strip", "at (mm)", "gap margin", "at (mm)", "verdict"))

rows = []
for name in SIG:
    t0 = time.time()
    items = [t for t in tracks if t.GetNetname() != name]
    items += [p for p in pads if p.GetNetname() != name]
    g = probe.NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
    g.build(items)

    tgt = [t for t in tracks if t.GetNetname() == name]
    tgt += [p for p in pads if p.GetNetname() == name]
    cells = replan.cells_of(g, tgt, LAYERS)
    if not cells:
        rows.append((name, None, None, None, None))
        print("  %-6s %s" % (name, "no copper on the board"))
        continue
    copper = np.zeros((g.ny, g.nx), bool)
    for lay, i, j in cells:
        copper[j, i] = True

    out = []
    for kind in ("strip", "margin"):
        site = sites(kind)
        if not site.any():
            out.append((None, None, None))
            continue
        dt = probe.octile_dt(site, STEP) * STEP
        d = np.where(copper, dt, np.inf)
        k = np.unravel_index(int(np.argmin(d)), d.shape)
        gap = float(d[k])
        out.append((gap, g.x0 + k[1] * STEP, g.y0 + k[0] * STEP))

    gs, xs_, ys_ = out[0]
    gm, xm, ym = out[1]
    cand = min([v for v in (gs, gm) if v is not None] or [9e9])
    verdict = "candidate" if cand <= PAD_KEEP else "REJECT"
    rows.append((name, gs, xs_, gm, xm))
    print("  %-6s %9s %-18s %9s %-18s %s   (%.1fs)"
          % (name,
             "%.2f" % gs if gs is not None else "--",
             "(%.1f, %.1f)" % (xs_, ys_) if gs is not None else "",
             "%.2f" % gm if gm is not None else "--",
             "(%.1f, %.1f)" % (xm, ym) if gm is not None else "",
             verdict, time.time() - t0), flush=True)

print("\n=== union over the bottom strip ===")
st = sorted(r[0] for r in rows if r[1] is not None and r[1] <= PAD_KEEP)
print("  %d/31 reachable: %s" % (len(st), " ".join(st)))
mg = sorted(r[0] for r in rows if r[3] is not None and r[3] <= PAD_KEEP)
print("=== union over the margins ===")
print("  %d/31 reachable: %s" % (len(mg), " ".join(mg)))
print("=== union of both ===")
bo = sorted(set(st) | set(mg))
print("  %d/31 reachable" % len(bo))
print("  still unreachable: %s"
      % (" ".join(n for n in SIG if n not in bo) or "(none)"))
