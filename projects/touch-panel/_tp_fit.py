"""Largest empty rectangles on the touch panel -- where can four SOIC-16s go?

Occupancy maps answer "is this spot free" one spot at a time.  The placement
question is the other way round: hand me the biggest holes.  So rasterise the
board at half a millimetre and run the standard largest-rectangle-in-a-histogram
sweep over two occupancy sets:

    clear  -- no footprint, no track, no pad, no via, no copper graphic
    bare   -- no footprint (copper may be crossed, at the cost of re-routing)

A 74HC595 in SOIC-16 with its courtyard needs about 11.0 x 6.0 mm; a 0402
needs about 1.6 x 0.9.  Report the biggest holes and whether the chip fits.

  python _tp_fit.py [--cell 0.5] [--top 20]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
CELL = 0.5
TOP = 20
argv = sys.argv[1:]
if "--cell" in argv:
    CELL = float(argv[argv.index("--cell") + 1])
if "--top" in argv:
    TOP = int(argv[argv.index("--top") + 1])

CHIP_W, CHIP_H = 11.0, 6.0          # SOIC-16 with courtyard
PAD_MARGIN = 0.25                   # keep clear of the neighbouring copper

b = pcbnew.LoadBoard(PCB)
box = b.GetBoardEdgesBoundingBox()
X0, Y0 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
NX = int(pcbnew.ToMM(box.GetWidth()) / CELL)
NY = int(pcbnew.ToMM(box.GetHeight()) / CELL)
print("board %.2f x %.2f mm, raster %d x %d cells of %.2f mm"
      % (pcbnew.ToMM(box.GetWidth()), pcbnew.ToMM(box.GetHeight()),
         NX, NY, CELL))

# --- occupancy ------------------------------------------------------------
bare = [[True] * NX for _ in range(NY)]     # no footprint
clear = [[True] * NX for _ in range(NY)]    # no footprint and no copper


def block(mask, ax0, ay0, ax1, ay1, margin=0.0):
    ix0 = max(0, int((ax0 - X0 - margin) / CELL))
    ix1 = min(NX - 1, int((ax1 - X0 + margin) / CELL))
    iy0 = max(0, int((ay0 - Y0 - margin) / CELL))
    iy1 = min(NY - 1, int((ay1 - Y0 + margin) / CELL))
    for iy in range(iy0, iy1 + 1):
        row = mask[iy]
        for ix in range(ix0, ix1 + 1):
            row[ix] = False


def bbox_rect(o):
    r = o.GetBoundingBox()
    return (pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY()),
            pcbnew.ToMM(r.GetX() + r.GetWidth()),
            pcbnew.ToMM(r.GetY() + r.GetHeight()))


for fp in b.GetFootprints():
    block(bare, *bbox_rect(fp), PAD_MARGIN)

for o in list(b.GetTracks()) + list(b.GetDrawings()):
    if o.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
        block(clear, *bbox_rect(o), PAD_MARGIN)
    if o.GetLayer() in (pcbnew.Edge_Cuts,):
        # keep footprints off the board edge
        block(bare, *bbox_rect(o), 0.6)
        block(clear, *bbox_rect(o), 0.6)

for fp in b.GetFootprints():
    for p in fp.Pads():
        block(clear, *bbox_rect(p), PAD_MARGIN)
    for g in list(fp.GraphicalItems()):
        if g.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
            block(clear, *bbox_rect(g), PAD_MARGIN)


def largest(mask, minw, minh):
    """Biggest all-true rectangle at least minw x minh cells, histogram sweep."""
    minw = max(1, int(minw / CELL))
    minh = max(1, int(minh / CELL))
    best = None
    heights = [0] * NX
    for iy in range(NY):
        row = mask[iy]
        for ix in range(NX):
            heights[ix] = heights[ix] + 1 if row[ix] else 0
        # for each cell as the bottom-right, expand left while the height holds
        for ix in range(NX):
            h = heights[ix]
            if h < minh:
                continue
            wmin = h
            for jx in range(ix, -1, -1):
                if heights[jx] < h:
                    break
                wmin = heights[jx] if heights[jx] < wmin else wmin
                w = ix - jx + 1
                if w < minw or wmin < minh:
                    continue
                area = w * wmin
                if best is None or area > best[0]:
                    best = (area, jx, iy - wmin + 1, w, wmin)
    return best


for label, mask in (("clear", clear), ("bare", bare)):
    print("\n=== %s" % label)
    m = largest(mask, CHIP_W, CHIP_H)
    if m:
        area, ix, iy, w, h = m
        print("   biggest rect fitting a chip: x %.2f..%.2f  y %.2f..%.2f"
              "  (%.2f x %.2f mm)"
              % (X0 + ix * CELL, X0 + (ix + w) * CELL,
                 Y0 + iy * CELL, Y0 + (iy + h) * CELL, w * CELL, h * CELL))
    else:
        print("   no rectangle %.1f x %.1f mm anywhere" % (CHIP_W, CHIP_H))

    # free space per horizontal band, so a long thin hole is still visible
    print("   free area by band (20 mm), as %% of band:")
    band = int(20.0 / CELL)
    for iy in range(0, NY, band):
        cnt = sum(1 for r in mask[iy:iy + band] for v in r if v)
        tot = sum(1 for r in mask[iy:iy + band] for _ in r)
        print("      y %6.2f..%6.2f  %5.1f%%"
              % (Y0 + iy * CELL, Y0 + min(iy + band, NY) * CELL,
                 100.0 * cnt / tot))

# --- a plain coarse map of the wholly-clear cells -------------------------
print("\n=== clear map, 4 mm cells   ' '=clear(any copper ok)  '#'=blocked")
C = 4.0
nx, ny = int(NX * CELL / C), int(NY * CELL / C)
hdr = "        " + "".join("%-4d" % int(X0 + i * C) for i in range(0, nx, 2))
print(hdr)
for iy in range(ny):
    line = ""
    for ix in range(nx):
        cnt = tot = 0
        for yy in range(int(iy * C / CELL), int((iy + 1) * C / CELL)):
            for xx in range(int(ix * C / CELL), int((ix + 1) * C / CELL)):
                tot += 1
                cnt += 1 if clear[yy][xx] else 0
        line += "  # " if cnt == 0 else ("  . " if cnt > tot * 0.98 else "  + ")
    print("%7.0f %s" % (Y0 + iy * C, line))
