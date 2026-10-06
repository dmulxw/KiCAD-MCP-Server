"""Draw the pocket ROW16/ROW17 are sealed inside, at 0.1mm per character.

A* expanded 234 cells and stopped 0.75mm short of the strip.  234 cells is not
a corridor pinching shut, it is a small closed room -- and a room is something
you can look at.  So instead of another listing of tracks, flood the legal free
space from the net's own stub end and print it.  The seal becomes visible as
whatever wall the flood runs into, and which net owns that wall is one more
call to the same dump.

Legend:  '#' own copper the wire may land on   '.' free space reachable from
         the stub end   'o' free space walled off from it   ' ' illegal
         (inside some other net's keep-out)   'M' a via is legal here
"""
import os
import sys

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

NAME = sys.argv[1] if len(sys.argv) > 1 else "ROW16"
X0, X1 = float(os.environ.get("TP_X0", "131")), float(os.environ.get("TP_X1", "137"))
Y0, Y1 = float(os.environ.get("TP_Y0", "241.5")), float(os.environ.get("TP_Y1", "246"))
PAD = (float(os.environ.get("TP_PX", "133.75")),
       float(os.environ.get("TP_PY", "243.15")))
BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard(%s) returned None" % BOARD)

keep_alive = []
if os.environ.get("TP_DROP_J1"):
    gone = [f for f in board.GetFootprints() if f.GetReference() == "J1"]
    for f in gone:
        board.Remove(f)
    keep_alive.extend(gone)

EXT = float(os.environ.get("TP_EXTEND_DOWN", "0"))
if EXT:
    ys = [pt.y for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts
          for pt in (d.GetStart(), d.GetEnd())]
    YMAX = max(ys)
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        a, b2 = d.GetStart(), d.GetEnd()
        if abs(a.y - b2.y) < 1:
            continue
        for pt in (a, b2):
            if abs(pt.y - YMAX) < 1:
                pt.y = int(round(pt.y + EXT * S))
        d.SetStart(a)
        d.SetEnd(b2)

tracks = list(board.GetTracks())
pads = [p for f in board.GetFootprints() for p in f.Pads()]

items = [t for t in tracks if t.GetNetname() != NAME]
items += [p for p in pads if p.GetNetname() != NAME]
g = probe.NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
g.build(items)

tgt = [t for t in tracks if t.GetNetname() == NAME]
tgt += [p for p in pads if p.GetNetname() == NAME]
own = replan.cells_of(g, tgt, LAYERS)


def cell(x, y):
    return (int(round((x - g.x0) / STEP)), int(round((y - g.y0) / STEP)))


# --- where a wire may walk, and where it may land, on the net's own layer set
walk = {lay: g.OK[lay].copy() for lay in LAYERS}
land = {lay: np.zeros_like(g.OK[lay]) for lay in LAYERS}
for lay, i, j in own:
    if 0 <= j < g.ny and 0 <= i < g.nx and walk[lay][j, i]:
        land[lay][j, i] = True

# --- flood from legal cells on the net's copper near the removed pad site
px, py = PAD
seen = {lay: np.zeros_like(g.OK[lay]) for lay in LAYERS}
stack = []
for lay in LAYERS:
    for lay2, i, j in own:
        if lay2 != lay:
            continue
        x, y = g.x0 + i * STEP, g.y0 + j * STEP
        if (x - px) ** 2 + (y - py) ** 2 <= 0.5 ** 2 and y >= 242.5 \
                and walk[lay][j, i]:
            seen[lay][j, i] = True
            stack.append((lay, i, j))

n = 0
while stack:
    lay, i, j = stack.pop()
    n += 1
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ni, nj = i + di, j + dj
        if 0 <= ni < g.nx and 0 <= nj < g.ny and walk[lay][nj, ni] \
                and not seen[lay][nj, ni]:
            seen[lay][nj, ni] = True
            stack.append((lay, ni, nj))
    if g.VOK[j, i]:
        for other in LAYERS:
            if other != lay and walk[other][j, i] and not seen[other][j, i]:
                seen[other][j, i] = True
                stack.append((other, i, j))

print("=== %s: flood from (%.3f, %.3f) ===" % (NAME, px, py))
print("  reachable free cells: %d  (%.2f mm2)"
      % (n, n * STEP * STEP))

i0 = cell(X0, Y0)[0]
i1 = cell(X1, Y0)[0]
j0 = cell(X0, Y0)[1]          # smaller y -- printed first
j1 = cell(X0, Y1)[1]          # larger y -- printed last
wide = i1 - i0 + 1
for lay in LAYERS:
    print("\n--- %s   x %.2f..%.2f  y %.2f..%.2f ---"
          % ("F.Cu" if lay == pcbnew.F_Cu else "B.Cu", X0, X1, Y0, Y1))
    tick = [" "] * wide
    label = [" "] * wide
    for k in range(wide):
        if (i0 + k) % 10 == 0:
            s = "%.0f" % (X0 + k * STEP)
            for m, ch in enumerate(s):
                if k + m < wide:
                    label[k + m] = ch
            tick[k] = "|"
    print("          " + "".join(label))
    print("          " + "".join(tick))
    for j in range(j0, j1 + 1):
        row = []
        for i in range(i0, i1 + 1):
            if not walk[lay][j, i]:
                row.append(" ")
            elif land[lay][j, i]:
                row.append("#")
            elif seen[lay][j, i]:
                row.append("M" if g.VOK[j, i] else ".")
            else:
                row.append("o")
        print("  %7.2f %s" % (g.y0 + j * STEP, "".join(row)))
