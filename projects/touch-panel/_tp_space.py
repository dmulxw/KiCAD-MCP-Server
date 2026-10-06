"""Where is there room on the touch panel for four SOIC-16s?

The board is a keyboard: 220 keys on a dense grid, and the shift registers have
to land somewhere that is both empty and close enough to J1A/J1B to route to.
Print an occupancy map of the footprint courtyards so the landing zone is read
off the board rather than guessed at.

  python _tp_space.py [--cell 5]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
CELL = 5.0
if "--cell" in sys.argv:
    CELL = float(sys.argv[sys.argv.index("--cell") + 1])

b = pcbnew.LoadBoard(PCB)
box = b.GetBoardEdgesBoundingBox()
x0, y0 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
x1 = x0 + pcbnew.ToMM(box.GetWidth())
y1 = y0 + pcbnew.ToMM(box.GetHeight())
print("board %.2f x %.2f mm   x %.2f..%.2f   y %.2f..%.2f"
      % (x1 - x0, y1 - y0, x0, x1, y0, y1))
print("footprints %d, tracks %d, zones %d"
      % (len(b.GetFootprints()), len(b.GetTracks()), b.GetAreaCount()))

nx = int((x1 - x0) / CELL) + 1
ny = int((y1 - y0) / CELL) + 1
grid = [["." for _ in range(nx)] for _ in range(ny)]

areas = {}
for fp in b.GetFootprints():
    ref = fp.GetReference()
    bb = fp.GetBoundingBox()
    ax0 = pcbnew.ToMM(bb.GetX())
    ay0 = pcbnew.ToMM(bb.GetY())
    ax1 = ax0 + pcbnew.ToMM(bb.GetWidth())
    ay1 = ay0 + pcbnew.ToMM(bb.GetHeight())
    areas[ref] = (ax0, ay0, ax1, ay1, str(fp.GetFPID()), fp.GetLayerName())
    for iy in range(ny):
        for ix in range(nx):
            cx = x0 + (ix + 0.5) * CELL
            cy = y0 + (iy + 0.5) * CELL
            if ax0 <= cx <= ax1 and ay0 <= cy <= ay1:
                grid[iy][ix] = "#"

# Tracks count as occupied too: a footprint dropped on top of a trace is a
# short, and the panel is routed already.
for t in b.GetTracks():
    bb = t.GetBoundingBox()
    ax0 = pcbnew.ToMM(bb.GetX())
    ay0 = pcbnew.ToMM(bb.GetY())
    ax1 = ax0 + pcbnew.ToMM(bb.GetWidth())
    ay1 = ay0 + pcbnew.ToMM(bb.GetHeight())
    for iy in range(ny):
        for ix in range(nx):
            cx = x0 + (ix + 0.5) * CELL
            cy = y0 + (iy + 0.5) * CELL
            if ax0 <= cx <= ax1 and ay0 <= cy <= ay1:
                if grid[iy][ix] == ".":
                    grid[iy][ix] = "-"

print("\noccupancy, %.0f mm cells   '#' footprint   '-' copper only   '.' free"
      % CELL)
hdr = "      " + "".join("%-4d" % int(x0 + i * CELL) for i in range(0, nx, 4))
print("      " + "".join("%-4s" % ((int(x0 + i * CELL) // 10) % 10)
                         for i in range(nx)))
for iy in range(ny):
    print("%5d %s" % (int(y0 + iy * CELL),
                      "".join("%-4s" % grid[iy][ix] for ix in range(nx))))

print("\nlargest free runs (cell centres):")
for iy in range(ny):
    ix = 0
    while ix < nx:
        if grid[iy][ix] == ".":
            s = ix
            while ix < nx and grid[iy][ix] == ".":
                ix += 1
            if ix - s >= 4:
                print("   y=%5d  x %5d..%5d  (%.0f mm)"
                      % (int(y0 + iy * CELL), int(x0 + s * CELL),
                         int(x0 + (ix - 1) * CELL), (ix - s) * CELL))
        else:
            ix += 1

print("\nkey references:")
for ref in ("J1", "J1A", "J1B", "MK1", "MK2", "MK3"):
    if ref in areas:
        a = areas[ref]
        print("   %-4s (%.2f,%.2f)-(%.2f,%.2f)  %s  %s"
              % (ref, a[0], a[1], a[2], a[3], a[4], a[5]))
