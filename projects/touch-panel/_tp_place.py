"""Where on the touch panel can a small SOIC land?  Exact, and fast.

Earlier attempts rasterised bounding boxes, which for a diagonal track is the
whole rectangle the diagonal spans; that over-blocks badly and hid real space.
This one samples geometry that has a tight extent:

    tracks   points along the segment, each lighting a disc of half its width
    vias     a disc
    pads     their bounding box (a pad is a rectangle, oval or circle -- tight)
    parts    their F.CrtYd bounding box, so reference text does not block

Then it reports, per copper layer, the largest rectangles that are clear of
that layer's copper and of every courtyard, and how many pieces of the named
size fit in each.

  python _tp_place.py [--cell 0.25] [--w 7.5] [--h 10.4] [--band 10]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

argv = sys.argv[1:]


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


CELL = opt("--cell", 0.25)
WANT_W = opt("--w", 7.5)
WANT_H = opt("--h", 10.4)

b = pcbnew.LoadBoard(PCB)
box = b.GetBoardEdgesBoundingBox()
X0, Y0 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
BW, BH = pcbnew.ToMM(box.GetWidth()), pcbnew.ToMM(box.GetHeight())
NX, NY = int(BW / CELL) + 1, int(BH / CELL) + 1
print("board %.2f x %.2f mm  raster %d x %d at %.2f mm" % (BW, BH, NX, NY, CELL))

cu = {pcbnew.F_Cu: bytearray(NX * NY), pcbnew.B_Cu: bytearray(NX * NY)}
crt = bytearray(NX * NY)
EDGE = 0.5          # keep parts this far off the board edge


def blob(grid, ax0, ay0, ax1, ay1, margin=0.0, rm=False):
    ix0 = max(0, int((ax0 - margin - X0) / CELL))
    ix1 = min(NX - 1, int((ax1 + margin - X0) / CELL))
    iy0 = max(0, int((ay0 - margin - Y0) / CELL))
    iy1 = min(NY - 1, int((ay1 + margin - Y0) / CELL))
    for iy in range(iy0, iy1 + 1):
        base = iy * NX
        if rm:
            for ix in range(ix0, ix1 + 1):
                crt[base + ix] = 1
        else:
            for ix in range(ix0, ix1 + 1):
                grid[base + ix] = 1


def dot(grid, x, y, r):
    ix0 = max(0, int((x - r - X0) / CELL))
    ix1 = min(NX - 1, int((x + r - X0) / CELL))
    iy0 = max(0, int((y - r - Y0) / CELL))
    iy1 = min(NY - 1, int((y + r - Y0) / CELL))
    r2 = r * r
    for iy in range(iy0, iy1 + 1):
        cy = Y0 + (iy + 0.5) * CELL
        base = iy * NX
        for ix in range(ix0, ix1 + 1):
            cx = X0 + (ix + 0.5) * CELL
            if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                grid[base + ix] = 1


def rectof(o):
    r = o.GetBoundingBox()
    ax, ay = pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY())
    return ax, ay, ax + pcbnew.ToMM(r.GetWidth()), ay + pcbnew.ToMM(r.GetHeight())


for t in b.GetTracks():
    lay = t.GetLayer()
    g = cu.get(lay)
    if g is None:
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        dot(g, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
            pcbnew.ToMM(t.GetWidth(t.GetLayer())) / 2.0)
        continue
    s, e = t.GetStart(), t.GetEnd()
    ax, ay = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
    bx, by = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
    w = pcbnew.ToMM(t.GetWidth()) / 2.0
    n = max(1, int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / (CELL / 2.0)))
    for k in range(n + 1):
        f = k / float(n)
        dot(g, ax + (bx - ax) * f, ay + (by - ay) * f, w)

for fp in b.GetFootprints():
    for p in fp.Pads():
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            if p.IsOnLayer(lay):
                blob(cu[lay], *rectof(p))
    for it in fp.GraphicalItems():
        g = cu.get(it.GetLayer())
        if g is not None:
            blob(g, *rectof(it))
    poly = fp.GetCourtyard(pcbnew.F_CrtYd)
    if poly.OutlineCount():
        r = poly.BBox()
        ax, ay = pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY())
        blob(crt, ax, ay, ax + pcbnew.ToMM(r.GetWidth()),
             ay + pcbnew.ToMM(r.GetHeight()))

for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        blob(crt, *rectof(d), EDGE, rm=True)


def largest(grid, minw, minh):
    """Biggest true rectangle at least minw x minh cells, histogram sweep."""
    out = []
    heights = [0] * NX
    for iy in range(NY):
        base = iy * NX
        for ix in range(NX):
            heights[ix] = heights[ix] + 1 if not grid[base + ix] else 0
        stack = []
        for ix in range(NX + 1):
            h = heights[ix] if ix < NX else 0
            start = ix
            while stack and stack[-1][1] > h:
                sx, sh = stack.pop()
                if sh >= minh and ix - sx >= minw:
                    out.append((sx, iy - sh + 1, ix - sx, sh))
                start = sx
            stack.append((start, h))
    return out


for name, lay in (("F.Cu", pcbnew.F_Cu), ("B.Cu", pcbnew.B_Cu)):
    grid = bytearray(NX * NY)
    for i in range(NX * NY):
        grid[i] = cu[lay][i] or crt[i]
    minw, minh = int(WANT_W / CELL), int(WANT_H / CELL)
    rs = largest(grid, minw, minh)
    # keep only maximal ones
    kept = []
    for sx, sy, w, h in sorted(rs, key=lambda r: -r[2] * r[3]):
        r = (sx, sy, w, h)
        if any(sx >= k[0] and sy >= k[1] and sx + w <= k[0] + k[2]
               and sy + h <= k[1] + k[3] for k in kept):
            continue
        kept.append(r)
    print("\n=== %s : %d maximal free area(s) of at least %.1f x %.1f mm"
          % (name, len(kept), WANT_W, WANT_H))
    for sx, sy, w, h in kept[:12]:
        print("   x %7.2f..%7.2f  y %7.2f..%7.2f   %6.2f x %6.2f mm"
              % (X0 + sx * CELL, X0 + (sx + w) * CELL,
                 Y0 + sy * CELL, Y0 + (sy + h) * CELL, w * CELL, h * CELL))
