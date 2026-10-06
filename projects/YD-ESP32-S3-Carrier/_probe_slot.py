"""Where could a 0603 legally sit?

R7 (IO10) and R8 (IO11) are sealed east of the two parallel +3V3 diagonals that
cross the audio-module no-via box.  Moving them west of that wall, or out of the
box, would let them route out on F.Cu with no via at all -- but only if there is
actually free copper area to put them on.

This builds the router's own obstacle mask with no own-net exclusion (so every
real net blocks), then marks each cell where a disc of R_MM is entirely clear.
A surviving cell is somewhere a part's copper could land without breaking CLEAR.
Clusters of such cells are the candidate sites.

  python _probe_slot.py
"""
import sys
from collections import deque

import numpy as np
import pcbnew

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts")
import route

R_MM = 0.80          # pad half-diagonal (0.62) plus a little margin
HW = 0.15            # pretend the part's copper is a 0.30 trace
X0, X1, Y0, Y1 = 30.0, 82.0, 4.0, 46.0
STEP = 10            # ASCII map: one char per STEP cells (2 mm)

board = pcbnew.LoadBoard(route.BOARD)
router = route.Router(board)
route.absorb(board, router)

# hw = 0.15 => obstacles inflated by CLEAR + 0.15 = 0.31 mm
blocked, _ = router.blocked_for("__nothing__", HW)
free = ~blocked[0]                                  # F.Cu only

r = int(round(R_MM / route.GRID))                   # disc radius in cells
print("disc radius %d cell(s) = %.2f mm;  obstacles inflated by %.2f mm"
      % (r, r * route.GRID, route.CLEAR + HW))

i0, i1 = int(X0 / route.GRID), int(X1 / route.GRID)
j0, j1 = int(Y0 / route.GRID), int(Y1 / route.GRID)

# offsets of a disc of radius r
offs = [(di, dj) for di in range(-r, r + 1) for dj in range(-r, r + 1)
        if di * di + dj * dj <= r * r]

fits = np.zeros((route.NX, route.NY), dtype=bool)
for i in range(i0, i1 + 1):
    for j in range(j0, j1 + 1):
        if not free[i, j]:
            continue
        if all(0 <= i + di < route.NX and 0 <= j + dj < route.NY
               and free[i + di, j + dj] for di, dj in offs):
            fits[i, j] = True

print("cells that fit a %.2f mm disc: %d" % (R_MM, int(fits.sum())))

# cluster them
seen = set()
clusters = []
for i in range(i0, i1 + 1):
    for j in range(j0, j1 + 1):
        if not fits[i, j] or (i, j) in seen:
            continue
        comp, q = [], deque([(i, j)])
        seen.add((i, j))
        while q:
            a, b = q.popleft()
            comp.append((a, b))
            for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p = (a + da, b + db)
                if p in seen or not (i0 <= p[0] <= i1 and j0 <= p[1] <= j1):
                    continue
                if fits[p[0], p[1]]:
                    seen.add(p)
                    q.append(p)
        clusters.append(comp)

clusters.sort(key=len, reverse=True)
print("\ntop candidate sites (largest free discs):")
for comp in clusters[:14]:
    xs = [c[0] * route.GRID for c in comp]
    ys = [c[1] * route.GRID for c in comp]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    print("   %5d cell(s)  bbox x[%6.2f..%6.2f] y[%6.2f..%6.2f]  centre (%6.2f, %6.2f)"
          % (len(comp), min(xs), max(xs), min(ys), max(ys), cx, cy))

print("\nmap (one char per %d cells = %.1f mm;  # = fits, . = blocked,"
      " + = VIA_BAN box):" % (STEP, STEP * route.GRID))
hdr = "        " + "".join("%-*s" % (STEP, "%d" % (X0 + k * STEP * route.GRID))
                           for k in range(int((X1 - X0) / (STEP * route.GRID)) + 1))
print(hdr)
for j in range(j1, j0 - 1, -STEP):
    row = ""
    for i in range(i0, i1 + 1, STEP):
        x, y = i * route.GRID, j * route.GRID
        if not (route.VIA_BAN[0][0] <= x <= route.VIA_BAN[0][2]
                and route.VIA_BAN[0][1] <= y <= route.VIA_BAN[0][3]):
            row += "."
            continue
        row += "#" if fits[i, j] else " "
    print("  y%5.1f  %s" % (j * route.GRID, row))
