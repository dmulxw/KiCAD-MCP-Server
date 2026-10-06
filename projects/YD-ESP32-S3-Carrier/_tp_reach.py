"""Is a net reachable from the strip at all?  A labelling, not a seventh sample.

The strip sweep answered "can a chip at THIS position reach net N" seven times,
and the union of those seven answers left five nets untouched from every one of
them: CSEL1 ROW8 ROW16 ROW17 ROW19.  A union of samples is not a proof that no
position works -- but free-space connectivity is.  If no legal cell on net N's
own copper lies in the same connected region of free space as the strip, then no
chip anywhere in the strip can reach N, because the chip's output pads are cells
in that strip region and its wire has to walk from there to the goal.

That is a labelling, not a search.  Take the same model _tp_drive.py uses --
same NGrid, same KEEP family, the net's own copper dissolved out of the
obstacles, goals = legal cells on the net's own copper -- then instead of
running A* from one chip, label the free space once and ask whether any goal
cell carries the same label as the strip.  Same model, so a "connected" verdict
here says exactly what a non-NO-PATH verdict says there, and an "isolated"
verdict is a proof rather than a sample.

The margin is measured the same way, because the panel also has its own headers
now: if a net is isolated from the strip but connected to the margin, the panel
can still feed it locally, which is a different (and cheaper) fix than a cable.
"""
import os
import sys
import time

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
import replan                                              # noqa: E402
import probe                                               # noqa: E402
from _tp_label import label_free                           # noqa: E402

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
eys = [pcbnew.ToMM(pt.y) for d in edges for pt in (d.GetStart(), d.GetEnd())]
exs = [pcbnew.ToMM(pt.x) for d in edges for pt in (d.GetStart(), d.GetEnd())]
print("outline: x %.2f..%.2f  y %.2f..%.2f" % (min(exs), max(exs),
                                               min(eys), max(eys)))
YMAX_MM = max(eys)

tracks = list(board.GetTracks())
pads = [p for f in board.GetFootprints() for p in f.Pads()]
print("board items: %d tracks, %d pads" % (len(tracks), len(pads)))

Y_STRIP = 244.0
XMARGIN = 98.0
XARR_HI = 169.0
Y_MARGIN_LO, Y_MARGIN_HI = 100.0, 250.0


def boxes(g):
    xs = g.x0 + np.arange(g.nx) * STEP
    ys = g.y0 + np.arange(g.ny) * STEP
    Y = ys[:, None]
    X = xs[None, :]
    strip = np.broadcast_to((Y >= Y_STRIP) & (Y <= YMAX_MM - 1.0),
                            (g.ny, g.nx))
    margin = np.broadcast_to(((X <= XMARGIN) | (X >= XARR_HI))
                             & (Y >= Y_MARGIN_LO) & (Y <= Y_MARGIN_HI),
                             (g.ny, g.nx))
    return strip, margin


def site_mask(g, want=0):
    """Cells where a whole 7.4 x 10.4mm chip courtyard is clear of copper.

    A component is only worth counting if a chip can actually stand in it.  A
    pocket of free space 6.3mm tall is free space, but it is not a placement:
    collect every label that appears inside the strip band and you union over
    pockets nobody can stand in, which is the same mistake as unioning pad
    reachability over x.  The chip's pads are F.Cu, so the courtyard square is
    tested against both layers' keep-out -- conservative, and in the strip below
    the array B.Cu is open anyway.
    """
    both = g.OK[pcbnew.F_Cu] & g.OK[pcbnew.B_Cu]
    h = int(round(10.4 / STEP))
    w = int(round(7.4 / STEP))
    ny, nx = both.shape
    S = np.zeros((ny, nx), bool)
    if ny < h or nx < w:
        return S
    c = np.pad(np.cumsum(np.cumsum(both.astype(np.int32), 0), 1), ((1, 0), (1, 0)))
    full = (c[h:, w:] - c[:-h, w:] - c[h:, :-w] + c[:-h, :-w]) == h * w
    j0, i0 = h // 2, w // 2
    S[j0:j0 + full.shape[0], i0:i0 + full.shape[1]] = full
    return S


def labels_in(g, comp, box, sit):
    """Components that both touch `box` and contain a chip site."""
    got = set()
    sel = sit & box
    if not sel.any():
        return got
    for lay in LAYERS:
        got |= set(np.unique(comp[lay][sel]).tolist())
    got.discard(-1)
    return got


def comp_bbox(g, comp, lay, k):
    idx = np.argwhere(comp[lay] == k)
    if not len(idx):
        return None
    j0, i0 = idx.min(0)
    j1, i1 = idx.max(0)
    return (g.x0 + i0 * STEP, g.y0 + j0 * STEP,
            g.x0 + i1 * STEP, g.y0 + j1 * STEP, len(idx))


print("\n%-6s %-9s %-9s  %s" % ("net", "strip", "margin", "goal component"))
rows = []
for name in SIG:
    t0 = time.time()
    items = [t for t in tracks if t.GetNetname() != name]
    items += [p for p in pads if p.GetNetname() != name]
    g = probe.NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
    g.build(items)
    comp, K = label_free(g.OK, g.VOK, LAYERS, g.nx, g.ny, quiet=True)

    box_strip, box_margin = boxes(g)
    sit = site_mask(g)
    lab_strip = labels_in(g, comp, box_strip, sit)
    lab_margin = labels_in(g, comp, box_margin, sit)
    if name == SIG[0]:
        for kind, box in (("strip", box_strip), ("margin", box_margin)):
            n = int((sit & box).sum())
            print("  [%s holds %d chip-site cells = %.0f chip footprints]"
                  % (kind, n, n * STEP * STEP / (7.4 * 10.4)), flush=True)

    tgt = [t for t in tracks if t.GetNetname() == name]
    tgt += [p for p in pads if p.GetNetname() == name]
    goals = [c for c in replan.cells_of(g, tgt, LAYERS)
             if g.OK[c[0]][c[2], c[1]]]

    gl = {}
    for lay, i, j in goals:
        gl.setdefault(comp[lay][j, i], []).append((lay, i, j))

    ok_strip = bool(set(gl) & lab_strip)
    ok_margin = bool(set(gl) & lab_margin)

    # the world the net's own copper lives in: the biggest goal component
    big = max(gl, key=lambda k: len(gl[k])) if gl else None
    note = ""
    if big is not None:
        best = None
        for lay in LAYERS:
            b = comp_bbox(g, comp, lay, big)
            if b and (best is None or b[4] > best[4]):
                best = b
        if best:
            note = ("#%d %d cells, x %.1f..%.1f y %.1f..%.1f"
                    % (big, best[4], best[0], best[2], best[1], best[3]))
        if big in lab_strip:
            note += "  [= strip]"
        if big in lab_margin:
            note += "  [= margin]"
    if not goals:
        note = "no legal goal cell at all"

    rows.append((name, ok_strip, ok_margin, len(goals), note))
    print("  %-6s %-9s %-9s  %s   (%.1fs)"
          % (name, "yes" if ok_strip else "NO", "yes" if ok_margin else "NO",
             note, time.time() - t0), flush=True)

st = [r[0] for r in rows if r[1]]
mg = [r[0] for r in rows if r[2]]
bo = sorted(set(st) | set(mg))
print("\n=== connected to the strip ===")
print("  %d/31: %s" % (len(st), " ".join(sorted(st))))
print("=== connected to the margins ===")
print("  %d/31: %s" % (len(mg), " ".join(sorted(mg))))
print("=== connected to either ===")
print("  %d/31" % len(bo))
print("  isolated from both: %s"
      % (" ".join(n for n in SIG if n not in bo) or "(none)"))
print("\n  strip-only:  %s"
      % (" ".join(sorted(set(st) - set(mg))) or "(none)"))
print("  margin-only: %s"
      % (" ".join(sorted(set(mg) - set(st))) or "(none)"))
