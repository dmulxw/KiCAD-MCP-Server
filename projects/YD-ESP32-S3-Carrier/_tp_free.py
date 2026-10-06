"""Is there room on the touch-panel board for four SOIC-16s and their caps?

Moving the 595s onto the touch-panel deletes the carrier's routing wall outright --
the 31 panel nets never exist there, and the carrier shrinks to a 6-wire link.  The
proposal stands or falls on one fact, which is whether the touch-panel has ~5 x 12.5
mm of clear area per chip plus caps.  The plan notes say its largest double-layer
blank rectangle is 9.20 x 2.20 mm, but that was measured before the board was widened
by 10 mm on each side, and it asked a routing question (1.35 mm from the outline),
not a placement one.

So measure it as a placement question: rasterise every footprint courtyard, mounting
hole, and Edge.Cuts, then find the largest free axis-aligned rectangles.  Copper is
deliberately not an obstacle -- a chip may sit over a GND zone or a track, since the
courtyard is what placement cares about.
"""
import numpy as np
import pcbnew

BOARD = "../touch-panel/touch-panel.kicad_pcb"
STEP = 0.25                                     # mm per cell
MIN_SIDE = 3.0                                  # ignore slivers

b = pcbnew.LoadBoard(BOARD)

xs, ys = [], []
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        for p in (d.GetStart(), d.GetEnd()):
            xs.append(pcbnew.ToMM(p.x))
            ys.append(pcbnew.ToMM(p.y))
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
print("board x %.3f..%.3f  y %.3f..%.3f  (%.1f x %.1f mm)"
      % (x0, x1, y0, y1, x1 - x0, y1 - y0))

NX = int((x1 - x0) / STEP) + 1
NY = int((y1 - y0) / STEP) + 1
cell = np.zeros((NX, NY), dtype=bool)           # True = occupied


def mark(box):
    ax0, ay0, ax1, ay1 = box
    i0 = max(0, int((ax0 - x0) / STEP))
    i1 = min(NX - 1, int((ax1 - x0) / STEP))
    j0 = max(0, int((ay0 - y0) / STEP))
    j1 = min(NY - 1, int((ay1 - y0) / STEP))
    if i1 >= i0 and j1 >= j0:
        cell[i0:i1 + 1, j0:j1 + 1] = True


nfp = 0
for fp in b.GetFootprints():
    bb = fp.GetBoundingBox(False, False)        # courtyard only, no text
    mark((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
          pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    nfp += 1
print("footprints %d" % nfp)

# Largest all-free axis-aligned rectangle, by the usual histogram sweep.  Run it
# once over the whole board and once over each edge strip, since a long thin strip
# is where four chips would actually go and a whole-board sweep would miss it.
def largest(mask):
    w, h = mask.shape
    best = (0.0, 0, 0, 0, 0, 0)
    heights = np.zeros(w, dtype=int)
    for j in range(h):
        heights = np.where(mask[:, j], heights + 1, 0)
        stack = []
        for i in range(w + 1):
            cur = heights[i] if i < w else 0
            start = i
            while stack and stack[-1][1] >= cur:
                k, hh = stack.pop()
                area = hh * (i - k)
                if hh >= MIN_SIDE / STEP and area > best[0]:
                    best = (area, k, j - hh + 1, i - 1, hh, i - k)
                start = k
            stack.append((start, cur))
    return best


free = ~cell
area, i0, j0, i1, j1, _ = largest(free)
print("\nlargest free rectangle: %.2f x %.2f mm at x %.2f, y %.2f"
      % ((i1 - i0 + 1) * STEP, (j1 - j0 + 1) * STEP, x0 + i0 * STEP, y0 + j0 * STEP))

for name, lo, hi in (("left  strip", x0, x0 + 18.0),
                     ("right strip", x1 - 18.0, x1),
                     ("middle", x0 + 18.0, x1 - 18.0)):
    a0 = max(0, int((lo - x0) / STEP))
    a1 = min(NX - 1, int((hi - x0) / STEP))
    area, i0, j0, i1, j1, _ = largest(free[a0:a1 + 1, :])
    print("%-12s x %7.2f..%7.2f   largest free %.2f x %.2f mm at x %.2f, y %.2f"
          % (name, lo, hi, (i1 - i0 + 1) * STEP, (j1 - j0 + 1) * STEP,
             x0 + (a0 + i0) * STEP, y0 + j0 * STEP))

# Four SOIC-16 at 12.5 mm pitch, rot 0, and four C_0603: what they need.
print("\nneeded: 4 x SOIC-16 courtyard 7.49 x 10.49 mm on the 12.5 mm pitch,")
print("        plus 4 x C_0603 3.00 x 1.55 mm -- so 50.0 x 10.49 mm plus caps.")
