"""Exact-geometry ASCII view of the panel's copper, per layer or both.

Rasterises real segment/circle geometry (never a bounding box), so a diagonal
track reads as a diagonal.  Pads are tested by real pad-shape hit where cheap,
otherwise by their own bbox on the one layer they occupy.

  python _tp_copper_map.py --bbox 90,100,112,250 --cell 0.40 --layer B
"""
import argparse
import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
TO = pcbnew.ToMM
F_CU, B_CU = pcbnew.F_Cu, pcbnew.B_Cu

ap = argparse.ArgumentParser()
ap.add_argument("--bbox", default="90,100,112,250")
ap.add_argument("--cell", type=float, default=0.40)
ap.add_argument("--layer", choices=["F", "B", "C"], default="C")
a = ap.parse_args()
x1, y1, x2, y2 = [float(v) for v in a.bbox.split(",")]
wantF = a.layer in ("F", "C")
wantB = a.layer in ("B", "C")

board = pcbnew.LoadBoard(BOARD)
S = 1e6


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - (ax + u * dx)) ** 2 + (py - (ay + u * dy)) ** 2) ** 0.5


segs = []   # (net, layer, ax, ay, bx, by, hw)
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    L = t.GetLayer()
    if (L == F_CU and not wantF) or (L == B_CU and not wantB):
        continue
    s, e = t.GetStart(), t.GetEnd()
    segs.append((t.GetNetname(), L, TO(s.x), TO(s.y), TO(e.x), TO(e.y),
                 TO(t.GetWidth()) / 2.0))

vias = []
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        continue
    s = t.GetStart()
    vias.append((t.GetNetname(), TO(s.x), TO(s.y), TO(t.GetWidth(F_CU)) / 2.0))

pads = []
for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNetname() == "":     # keep unconnected pads visible too
            pass
        L = F_CU if p.IsOnLayer(F_CU) else (B_CU if p.IsOnLayer(B_CU) else None)
        if L is None or (L == F_CU and not wantF) or (L == B_CU and not wantB):
            continue
        o = p.GetPosition()
        bb = p.GetBoundingBox()
        pads.append((p.GetNetname() or "?", f.GetReference(), str(p.GetNumber()),
                     TO(o.x), TO(o.y),
                     TO(bb.GetLeft()), TO(bb.GetTop()), TO(bb.GetRight()), TO(bb.GetBottom())))

POOL = "abcdefghijklmnopqrstuvwxyz0123456789!@$%&?~#^"
legend = {}


def glyph(net):
    if net not in legend:
        legend[net] = POOL[len(legend) % len(POOL)]
    return legend[net]


nx = int((x2 - x1) / a.cell) + 1
ny = int((y2 - y1) / a.cell) + 1
print("bbox (%.1f,%.1f)-(%.1f,%.1f)  cell %.2f  layer %s  %dx%d"
      % (x1, y1, x2, y2, a.cell, a.layer, nx, ny))

hdr = "      "
for i in range(nx):
    if i % 40 == 0:
        hdr += "%-10s" % ("%.0f" % (x1 + i * a.cell))
print(hdr)

for j in range(ny):
    cy = y1 + j * a.cell
    row = []
    for i in range(nx):
        cx = x1 + i * a.cell
        hit = None
        for (net, L, ax, ay, bx, by, hw) in segs:
            if seg_dist(cx, cy, ax, ay, bx, by) <= hw + a.cell * 0.45:
                hit = net
                break
        if hit is None:
            for (net, ref, num, px, py, l, t, r, b) in pads:
                if l - a.cell * 0.3 <= cx <= r + a.cell * 0.3 and \
                   t - a.cell * 0.3 <= cy <= b + a.cell * 0.3:
                    hit = net or "?"
                    break
        if hit is None:
            for (net, vx, vy, r) in vias:
                if (cx - vx) ** 2 + (cy - vy) ** 2 <= (r + a.cell * 0.45) ** 2:
                    hit = net
                    break
        row.append(glyph(hit) if hit else ".")
    print("%6.1f" % cy + "".join(row))

print("\nlegend:")
for k in sorted(legend, key=lambda n: legend[n]):
    print("   %s = %s" % (legend[k], k))
