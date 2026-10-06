"""How busy is each side of the touch panel, and where is each side free?

The front is packed with keys, but this is a two-layer board and a keyboard
does not usually route on both sides equally.  Before giving up on finding room
for four SOIC-16s, find out which layer the parts are on and which layer the
copper is on -- and then look for the largest free rectangle *per layer*, since
a part on the back only cares about the back.

  python _tp_layers.py [--cell 0.5]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
CELL = 0.5
if "--cell" in sys.argv:
    CELL = float(sys.argv[sys.argv.index("--cell") + 1])

b = pcbnew.LoadBoard(PCB)

print("=== footprints by layer")
by = {}
for fp in b.GetFootprints():
    by[fp.GetLayerName()] = by.get(fp.GetLayerName(), 0) + 1
for k in sorted(by):
    print("   %-10s %4d" % (k, by[k]))

print("\n=== pads by layer")
by = {}
for fp in b.GetFootprints():
    for p in fp.Pads():
        n = p.GetLayerSet().FmtHex()[:6]
        by[n] = by.get(n, 0) + 1
for k in sorted(by):
    print("   %-10s %4d" % (k, by[k]))

print("\n=== copper by layer")
LEN = {}
CNT = {}
for t in b.GetTracks():
    ln = b.GetLayerName(t.GetLayer())
    LEN[ln] = LEN.get(ln, 0.0) + pcbnew.ToMM(t.GetLength())
    CNT[ln] = CNT.get(ln, 0) + 1
for k in sorted(LEN):
    print("   %-10s %6d item(s)  %9.1f mm" % (k, CNT[k], LEN[k]))

print("\n=== zones")
for i in range(b.GetAreaCount()):
    z = b.GetArea(i)
    print("   %-20s %s" % (z.GetNetname(),
                           " ".join(b.GetLayerName(l)
                                    for l in z.GetLayerSet().Seq())))

box = b.GetBoardEdgesBoundingBox()
X0, Y0 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
NX = int(pcbnew.ToMM(box.GetWidth()) / CELL)
NY = int(pcbnew.ToMM(box.GetHeight()) / CELL)
print("\nboard x %.2f..%.2f  y %.2f..%.2f   raster %d x %d"
      % (X0, X0 + NX * CELL, Y0, Y0 + NY * CELL, NX, NY))


def rect(o):
    r = o.GetBoundingBox()
    return (pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY()),
            pcbnew.ToMM(r.GetX() + r.GetWidth()),
            pcbnew.ToMM(r.GetY() + r.GetHeight()))


def build(layer, margin=0.25):
    """Occupancy for one copper layer: footprints on it plus its own copper."""
    g = [[True] * NX for _ in range(NY)]

    def block(ax0, ay0, ax1, ay1):
        ix0 = max(0, int((ax0 - X0 - margin) / CELL))
        ix1 = min(NX - 1, int((ax1 - X0 + margin) / CELL))
        iy0 = max(0, int((ay0 - Y0 - margin) / CELL))
        iy1 = min(NY - 1, int((ay1 - Y0 + margin) / CELL))
        for iy in range(iy0, iy1 + 1):
            row = g[iy]
            for ix in range(ix0, ix1 + 1):
                row[ix] = False

    for fp in b.GetFootprints():
        if fp.IsOnLayer(layer):
            block(*rect(fp))
        for p in fp.Pads():
            if p.IsOnLayer(layer):
                block(*rect(p))
        for it in fp.GraphicalItems():
            if it.GetLayer() == layer:
                block(*rect(it))
    for o in list(b.GetTracks()) + list(b.GetDrawings()):
        if o.GetLayer() == layer:
            block(*rect(o))
    # board edge keepout
    for o in b.GetDrawings():
        if o.GetLayer() == pcbnew.Edge_Cuts:
            block(*rect(o))
    return g


def largest(mask):
    best = None
    heights = [0] * NX
    for iy in range(NY):
        row = mask[iy]
        for ix in range(NX):
            heights[ix] = heights[ix] + 1 if row[ix] else 0
        stack = []
        for ix in range(NX + 1):
            h = heights[ix] if ix < NX else 0
            start = ix
            while stack and stack[-1][1] > h:
                sx, sh = stack.pop()
                w = ix - sx
                area = w * sh
                if best is None or area > best[0]:
                    best = (area, sx, iy - sh + 1, w, sh)
                start = sx
            stack.append((start, h))
    return best


for name, layer in (("F.Cu", pcbnew.F_Cu), ("B.Cu", pcbnew.B_Cu)):
    g = build(layer)
    m = largest(g)
    if not m:
        print("\n=== %s: nothing free at all" % name)
        continue
    area, ix, iy, w, h = m
    print("\n=== %s : largest free rectangle  x %.2f..%.2f  y %.2f..%.2f"
          "  (%.2f x %.2f mm)"
          % (name, X0 + ix * CELL, X0 + (ix + w) * CELL,
             Y0 + iy * CELL, Y0 + (iy + h) * CELL, w * CELL, h * CELL))
    C = 4.0
    nx, ny = int(NX * CELL / C), int(NY * CELL / C)
    print("    4 mm cells:  '#'=blocked  '+'=partly free  '.'=free")
    for iy2 in range(ny):
        line = ""
        for ix2 in range(nx):
            cnt = tot = 0
            for yy in range(int(iy2 * C / CELL), int((iy2 + 1) * C / CELL)):
                for xx in range(int(ix2 * C / CELL), int((ix2 + 1) * C / CELL)):
                    tot += 1
                    cnt += 1 if g[yy][xx] else 0
            line += "  # " if cnt == 0 else ("  . " if cnt > tot * 0.985
                                             else "  + ")
        print("   %6.0f %s" % (Y0 + iy2 * C, line))
    print("          " + "".join("%-4d" % int(X0 + i * C)
                                 for i in range(0, nx, 2)))
