"""Draw it.  The numbers say chip A's flood fills the whole left strip and yet
touches only two of the thirty-one nets, which is either a wall or a puzzle, and
no table of distances distinguishes the two.  A picture does.

Each cell below is 2mm.  '#' is flooded free space, a letter is one of the
chip's own eight target nets, 'o' is any other net's copper.  What to look for
is whether a letter ever sits next to a '#'.
"""
import sys

import numpy as np
import pcbnew

sys.path.insert(0, "../touch-panel/work3")
from probe import NGrid                                   # noqa: E402

S = 1e6
F_Cu, B_Cu = pcbnew.F_Cu, pcbnew.B_Cu
LAYERS = [F_Cu, B_Cu]

STEP = 0.1
CLEAR, SAFETY = 0.20, 0.04
KEEP = CLEAR + 0.1 + SAFETY
PAD_KEEP = CLEAR + 0.3 + SAFETY
EGK = 0.50 + CLEAR + SAFETY
VEK = EGK + 0.3

TAG = sys.argv[1] if len(sys.argv) > 1 else "A"
RES = 2.0

PLACE = {
    "A": (96.5, 238.2, ["ROW20", "ROW19", "CSEL0", "CSEL1",
                        "CSEL2", "CSEL8", "CSEL7", "CSEL9"]),
    "B": (97.0, 207.2, ["ROW1", "CSEL4", "ROW16", "ROW12",
                        "ROW15", "ROW14", "ROW17", "ROW18"]),
    "C": (170.5, 171.2, ["ROW6", "ROW7", "ROW0", "ROW9",
                         "ROW10", "ROW11", "ROW8", "ROW13"]),
    "D": (172.5, 134.2, ["CSEL5", "CSEL3", "CSEL6", "ROW4",
                         "ROW5", "ROW3", "ROW2"]),
}
LIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty"
FP = "SOIC-16_3.9x9.9mm_P1.27mm"
OUT_PADS = {"15", "1", "2", "3", "4", "5", "6", "7"}

board = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")
items = list(board.GetTracks())
for fp in board.GetFootprints():
    items.extend(fp.Pads())
base = len(items)

placed, chip_idx = {}, {}
for tag, (cx, cy, _) in PLACE.items():
    fp = pcbnew.FootprintLoad(LIB, FP)
    fp.SetPosition(pcbnew.VECTOR2I(int(cx * S), int(cy * S)))
    fp.SetReference("U%s" % tag)
    board.Add(fp)
    placed[tag] = fp
    pads = list(fp.Pads())
    chip_idx[tag] = list(range(len(items), len(items) + len(pads)))
    items.extend(pads)
net_of = np.array([it.GetNetname() for it in items], dtype=object)

cx0, cy0, nets = PLACE[TAG]
drop = set(chip_idx[TAG])
g = NGrid(board, STEP, KEEP, EGK, PAD_KEEP, VEK, LAYERS)
g.build([it for k, it in enumerate(items) if k not in drop])

starts = {lay: np.zeros((g.ny, g.nx), bool) for lay in LAYERS}
for p in placed[TAG].Pads():
    if p.GetNumber() not in OUT_PADS:
        continue
    c = p.GetPosition()
    i, j = g.ij(c.x / S, c.y / S)
    starts[F_Cu][j, i] = True

seen = {lay: starts[lay].copy() for lay in LAYERS}
for _ in range(8000):
    nxt = {}
    for lay in LAYERS:
        s, ok = seen[lay], g.OK[lay]
        r = s.copy()
        r[1:, :] |= s[:-1, :]
        r[:-1, :] |= s[1:, :]
        r[:, 1:] |= s[:, :-1]
        r[:, :-1] |= s[:, 1:]
        r[1:, 1:] |= s[:-1, :-1] & ok[1:, 1:] & ok[:-1, 1:] & ok[1:, :-1]
        r[1:, :-1] |= s[:-1, 1:] & ok[1:, :-1] & ok[:-1, :-1] & ok[1:, 1:]
        r[:-1, 1:] |= s[1:, :-1] & ok[:-1, 1:] & ok[1:, 1:] & ok[:-1, :-1]
        r[:-1, :-1] |= s[1:, 1:] & ok[:-1, :-1] & ok[1:, :-1] & ok[:-1, 1:]
        nxt[lay] = (r & ok) | s
    # A via joins the two layers AT that cell, so arriving on EITHER layer is
    # enough to take it.  Requiring both (VOK & nxt[F] & nxt[B]) never enters a
    # pocket whose only entrance is its own via, and draws a frontier that stops
    # dead against open copper.
    viacell = g.VOK & np.logical_or.reduce([nxt[lay] for lay in LAYERS])
    moved = False
    for lay in LAYERS:
        new = nxt[lay] | viacell
        moved = moved or not np.array_equal(new, seen[lay])
        seen[lay] = new
    if not moved:
        break

reach = np.logical_or.reduce([seen[l] for l in LAYERS])
cop = np.zeros((g.ny, g.nx), bool)
target = np.zeros((g.ny, g.nx), np.int8)          # 0 none, k+1 for target k
for lay in LAYERS:
    o = g.OWN[lay]
    good = o >= 0
    idx = np.where(good, o, 0)
    nm = np.where(good, net_of[idx], "")
    cop |= good & (g.D[lay] <= 0.05)
    for k, n in enumerate(nets):
        target |= (good & (nm == n) & (g.D[lay] <= 0.05)).astype(np.int8) * (k + 1)

H = int((g.ny * STEP) / RES) + 1
W = int((g.nx * STEP) / RES) + 1
grid = np.full((H, W), " ", dtype="<U1")
SIZE = int(RES / STEP)


def stamp(mask, ch, only_if_blank=False):
    for jj in range(H):
        j0, j1 = jj * SIZE, min((jj + 1) * SIZE, g.ny)
        if j0 >= j1:
            continue
        rows = mask[j0:j1]
        for ii in range(W):
            i0, i1 = ii * SIZE, min((ii + 1) * SIZE, g.nx)
            if i0 >= i1 or not rows[:, i0:i1].any():
                continue
            if only_if_blank and grid[jj, ii] != " ":
                continue
            grid[jj, ii] = ch


stamp(cop, "o")
for k, n in enumerate(nets):
    stamp(target == (k + 1), "abcdefgh"[k])
stamp(reach, "#", only_if_blank=True)

print("chip %s at (%.1f, %.1f)   targets %s" % (TAG, cx0, cy0, " ".join(nets)))
print("legend: '#' flooded free space   a-h = this chip's nets   "
      "'o' = any other net's copper   ' ' = blocked (clearance or edge)")
print("each cell = %.0fmm; board x %.0f..%.0f, y %.0f..%.0f"
      % (RES, g.x0, g.x0 + (g.nx - 1) * STEP, g.y0, g.y0 + (g.ny - 1) * STEP))
print()
hdr = "      " + "".join(("%d" % (int((g.x0 + ii * RES) / 10) % 10))
                         for ii in range(W))
print(hdr)
for jj in range(H):
    print("%5d " % (g.y0 + jj * RES) + "".join(grid[jj]))
