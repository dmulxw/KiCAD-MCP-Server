"""Where can four SOIC-16s go, and which ROW/CSEL nets are already next to them?

  _tp_free.py found 14.25 x 79.25 mm of courtyard-free space on the right margin
  (x 167..181) and 11.00 x 19.00 mm on the left, but courtyard-free is not
  routing-free: the right strip already carries 1080 mm of F.Cu.  And the nets the
  595s would drive do not end at the chips -- they end at J1A (x 95.4, left) and
  J1B (x 175.6, right), 80 mm apart.  A chip bank on one side leaves the other
  side's nets a full crossing of the electrode array, which the design notes call
  the single most congested thing on this board.

So two questions, both answered by measurement rather than by the notes:

  1. how many disjoint SOIC-16-sized free rectangles each margin holds (top 4),
  2. which nets actually run through each margin today, as track length by net.

If the ROW/CSEL nets already reach both margins, the 595s can be split 2 + 2 and
each output joins a net that passes beside it.  If they only reach one margin, the
other half has to be carried across, and the proposal costs the same crossing it
was meant to avoid.
"""
import collections

import numpy as np
import pcbnew

b = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")

xs, ys = [], []
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        for p in (d.GetStart(), d.GetEnd()):
            xs.append(pcbnew.ToMM(p.x))
            ys.append(pcbnew.ToMM(p.y))
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
STEP = 0.25
NX = int((x1 - x0) / STEP) + 1
NY = int((y1 - y0) / STEP) + 1
occ = np.zeros((NX, NY), dtype=bool)
for fp in b.GetFootprints():
    bb = fp.GetBoundingBox(False, False)
    i0 = max(0, int((pcbnew.ToMM(bb.GetLeft()) - x0) / STEP))
    i1 = min(NX - 1, int((pcbnew.ToMM(bb.GetRight()) - x0) / STEP))
    j0 = max(0, int((pcbnew.ToMM(bb.GetTop()) - y0) / STEP))
    j1 = min(NY - 1, int((pcbnew.ToMM(bb.GetBottom()) - y0) / STEP))
    if i1 >= i0 and j1 >= j0:
        occ[i0:i1 + 1, j0:j1 + 1] = True


def top_rects(mask, n, min_w, min_h):
    """Greedy: find the largest free rectangle, blank it, repeat."""
    out = []
    m = mask.copy()
    for _ in range(n):
        w, h = m.shape
        best = None
        heights = np.zeros(w, dtype=int)
        for j in range(h):
            heights = np.where(m[:, j], heights + 1, 0)
            stack = []
            for i in range(w + 1):
                cur = heights[i] if i < w else 0
                start = i
                while stack and stack[-1][1] >= cur:
                    k, hh = stack.pop()
                    wi = i - k
                    if hh >= min_h and wi >= min_w:
                        if best is None or hh * wi > best[0]:
                            best = (hh * wi, k, j - hh + 1, wi, hh)
                    start = k
                stack.append((start, cur))
        if best is None:
            break
        _, k, jj, wi, hh = best
        out.append((k, jj, wi, hh))
        m[k:k + wi, jj:jj + hh] = False
    return out


SOIC_W, SOIC_H = int(7.49 / STEP), int(10.49 / STEP)   # rot 0, courtyard
print("SOIC-16 rot 0 needs %.2f x %.2f mm\n" % (SOIC_W * STEP, SOIC_H * STEP))

for name, lo, hi in (("left  margin x  90.0..104.0", 90.0, 104.0),
                     ("right margin x 166.8..181.0", 166.8, 181.0)):
    a0 = max(0, int((lo - x0) / STEP))
    a1 = min(NX - 1, int((hi - x0) / STEP))
    sub = ~occ[a0:a1 + 1, :]
    rects = top_rects(sub, 4, SOIC_W, SOIC_H)
    print("%s -- %d SOIC-16-shaped free rect(s):" % (name, len(rects)))
    for (k, jj, wi, hh) in rects:
        print("    %.2f x %.2f mm at x %.2f, y %.2f"
              % (wi * STEP, hh * STEP, x0 + (a0 + k) * STEP, y0 + jj * STEP))
    print()

for name, lo, hi in (("left", 90.0, 104.2), ("right", 166.8, 181.0)):
    lens = collections.Counter()
    for t in b.GetTracks():
        s, e = t.GetStart(), t.GetEnd()
        mx = (pcbnew.ToMM(s.x) + pcbnew.ToMM(e.x)) / 2
        if lo <= mx <= hi:
            lens[t.GetNetname()] += pcbnew.ToMM(t.GetLength())
    rows = sorted(lens.items(), key=lambda kv: -kv[1])[:14]
    print("%s margin -- track length by net (top 14 of %d nets):" % (name, len(lens)))
    for n, L in rows:
        print("    %-14s %7.1f mm" % (n or "(no net)", L))
    print()
