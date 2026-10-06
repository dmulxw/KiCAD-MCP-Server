"""Exact occupancy of the touch panel -- the placement probe that does not lie.

The earlier probes rasterised each object's *bounding box*, which for a diagonal
track is the whole rectangle the diagonal spans.  On a board routed with
diagonals that paints the map solid and makes every free-space measurement
worthless.  This one samples real geometry:

    tracks   -- points along the segment, each marking a disc of half its width
    vias     -- a disc
    pads     -- PAD.HitTest against the cell centre
    parts    -- FOOTPRINT.GetCourtyard(), so reference text does not block

Usage:
    python _tp_occ.py map  X0 Y0 X1 Y1 [--cell 1.0] [--layer F|B|C]
    python _tp_occ.py free X0 Y0 X1 Y1 [--layer F|B] [--clear 0.25]

`map`  prints an ASCII picture; `F`=front copper `B`=back `x`=both
       `o`=courtyard only (a part sits here)  `.`=free both sides.
`free` reports the largest rectangles free of copper on the requested layer,
       which is what a placement decision actually needs.
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

argv = sys.argv[1:]
MODE = argv[0]
NUM = [float(v) for v in argv[1:5]]
WX0, WY0, WX1, WY1 = NUM

CELL = 1.0
if "--cell" in argv:
    CELL = float(argv[argv.index("--cell") + 1])
CLEAR = 0.25
if "--clear" in argv:
    CLEAR = float(argv[argv.index("--clear") + 1])
LAYER = "C"
if "--layer" in argv:
    LAYER = argv[argv.index("--layer") + 1]

b = pcbnew.LoadBoard(PCB)

# grid 0 = front copper, 1 = back copper, 2 = courtyard
NX = max(1, int(round((WX1 - WX0) / CELL)))
NY = max(1, int(round((WY1 - WY0) / CELL)))
g = [[0] * NX for _ in range(NY)]
crt = [[False] * NX for _ in range(NY)]


def nm(mm):
    return pcbnew.FromMM(mm)


def cellof(x, y):
    return (int((x - WX0) / CELL), int((y - WY0) / CELL))


def dot(x, y, radius, bit):
    """Light every cell whose centre lies within radius of (x, y)."""
    r2 = radius * radius
    ix, iy = cellof(x, y)
    span = int(radius / CELL) + 1
    for jy in range(max(0, iy - span), min(NY - 1, iy + span) + 1):
        cy = WY0 + (jy + 0.5) * CELL
        for jx in range(max(0, ix - span), min(NX - 1, ix + span) + 1):
            cx = WX0 + (jx + 0.5) * CELL
            if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                g[jy][jx] |= bit


def segment(x0, y0, x1, y1, width):
    n = max(1, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / (CELL / 3.0)) + 1)
    for k in range(n + 1):
        f = k / float(n)
        dot(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, width / 2.0, BIT)


LOOP = 200  # cells per HitTest batch is unnecessary; HitTest is cheap


def blob(obj, bit, expand=0.0):
    r = obj.GetBoundingBox()
    ax0, ay0 = pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY())
    ax1 = ax0 + pcbnew.ToMM(r.GetWidth())
    ay1 = ay0 + pcbnew.ToMM(r.GetHeight())
    ix0 = max(0, int((ax0 - expand - WX0) / CELL) - 1)
    ix1 = min(NX - 1, int((ax1 + expand - WX0) / CELL) + 1)
    iy0 = max(0, int((ay0 - expand - WY0) / CELL) - 1)
    iy1 = min(NY - 1, int((ay1 + expand - WY0) / CELL) + 1)
    if ix1 < ix0 or iy1 < iy0:
        return
    acc = nm(expand)
    for iy in range(iy0, iy1 + 1):
        cy = WY0 + (iy + 0.5) * CELL
        for ix in range(ix0, ix1 + 1):
            cx = WX0 + (ix + 0.5) * CELL
            if obj.HitTest(pcbnew.VECTOR2I(nm(cx), nm(cy)), acc):
                g[iy][ix] |= bit


for lay, bit in ((pcbnew.F_Cu, 1), (pcbnew.B_Cu, 2)):
    BIT = bit
    for t in b.GetTracks():
        if t.GetLayer() != lay:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            dot(pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                pcbnew.ToMM(t.GetWidth()) / 2.0, BIT)
            continue
        s, e = t.GetStart(), t.GetEnd()
        segment(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
                pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
                pcbnew.ToMM(t.GetWidth()))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if not p.IsOnLayer(lay):
                continue
            blob(p, BIT)
        for it in fp.GraphicalItems():
            if it.GetLayer() == lay:
                blob(it, BIT)
    for d in b.GetDrawings():
        if d.GetLayer() == lay:
            blob(d, BIT)

for fp in b.GetFootprints():
    poly = fp.GetCourtyard(pcbnew.F_CrtYd)
    if poly.OutlineCount() == 0:
        continue
    box = poly.BBox()
    ax0, ay0 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
    ax1 = ax0 + pcbnew.ToMM(box.GetWidth())
    ay1 = ay0 + pcbnew.ToMM(box.GetHeight())
    ix0 = max(0, int((ax0 - WX0) / CELL))
    ix1 = min(NX - 1, int((ax1 - WX0) / CELL))
    iy0 = max(0, int((ay0 - WY0) / CELL))
    iy1 = min(NY - 1, int((ay1 - WY0) / CELL))
    for iy in range(iy0, iy1 + 1):
        cy = WY0 + (iy + 0.5) * CELL
        for ix in range(ix0, ix1 + 1):
            cx = WX0 + (ix + 0.5) * CELL
            if poly.Contains(pcbnew.VECTOR2I(nm(cx), nm(cy))):
                crt[iy][ix] = True

if MODE == "map":
    CH = {0: ".", 4: "o", 5: "o", 6: "o", 7: "o"}
    print("x %.1f..%.1f  y %.1f..%.1f  cell %.2f   . free  F front  B back"
          "  x both  o part" % (WX0, WX1, WY0, WY1, CELL))
    print("      " + "".join("%d" % (int(WX0 + (i + 0.5) * CELL) // 10 % 10)
                             for i in range(NX)))
    print("      " + "".join("%d" % (int(WX0 + (i + 0.5) * CELL) % 10)
                             for i in range(NX)))
    for iy in range(NY):
        line = ""
        for ix in range(NX):
            v = g[iy][ix]
            if v == 0:
                line += "o" if crt[iy][ix] else "."
            elif v == 1:
                line += "F"
            elif v == 2:
                line += "B"
            else:
                line += "x"
        print("%6.1f %s" % (WY0 + iy * CELL, line))
    raise SystemExit(0)

# ---- free rectangles -------------------------------------------------------
print("window x %.2f..%.2f y %.2f..%.2f  cell %.2f  clearance %.2f"
      % (WX0, WX1, WY0, WY1, CELL, CLEAR))
for name, bit in (("F.Cu", 1), ("B.Cu", 2), ("both", 3)):
    ok = [[(g[iy][ix] & bit) == 0 for ix in range(NX)] for iy in range(NY)]
    print("\n=== free of %s copper" % name)
    heights = [0] * NX
    best = None
    for iy in range(NY):
        for ix in range(NX):
            heights[ix] = heights[ix] + 1 if ok[iy][ix] else 0
        stack = []
        for ix in range(NX + 1):
            h = heights[ix] if ix < NX else 0
            start = ix
            while stack and stack[-1][1] > h:
                sx, sh = stack.pop()
                w = ix - sx
                if best is None or w * sh > best[0]:
                    best = (w * sh, sx, iy - sh + 1, w, sh)
                start = sx
            stack.append((start, h))
    if best:
        a, ix, iy, w, h = best
        print("   largest rectangle: x %.2f..%.2f  y %.2f..%.2f  (%.2f x %.2f)"
              % (WX0 + ix * CELL, WX0 + (ix + w) * CELL,
                 WY0 + iy * CELL, WY0 + (iy + h) * CELL, w * CELL, h * CELL))
