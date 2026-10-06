"""Draw the copper around a region so the gap blocking a repair is visible.

A via needs somewhere to sit, and this pair of stranded islands has nowhere:
the F.Cu half overlaps the main plane on six grid points and none of them has
room for a 0.6 mm via, which means the two layers are cut off together and the
patch is enclosed.  Enclosure is a question about what surrounds it, and that is
what a picture answers and a count does not.

Ground fill is labelled per island (the legend maps the character back to a
layer and index), so the gap between the stranded copper and the plane is
readable directly.  Everything else is labelled by net, because the net doing
the blocking decides whether a track can go round it or cannot.

  python _car_stranded_map.py --layer B --bbox 34,10,52,26
  python _car_stranded_map.py --layer F --bbox 34,10,64,34 --cell 0.35
"""
import argparse

import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
TO = pcbnew.ToMM
F_CU, B_CU = pcbnew.F_Cu, pcbnew.B_Cu

ap = argparse.ArgumentParser()
ap.add_argument("--layer", choices=["F", "B"], default="B")
ap.add_argument("--bbox", default="34,10,52,26", help="x1,y1,x2,y2 in mm")
ap.add_argument("--cell", type=float, default=0.25, help="mm per character")
a = ap.parse_args()

x1, y1, x2, y2 = [float(v) for v in a.bbox.split(",")]
layer = F_CU if a.layer == "F" else B_CU

board = pcbnew.LoadBoard(BOARD)


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


# -- ground fill, one label per island ------------------------------------
# Islands take capitals and every other net takes a lowercase/punctuation
# glyph: the first letter of a net name is not unique here, and half a dozen
# different IO nets all began with the same character.
GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
islands = []
for z in board.Zones():
    if z.GetIsRuleArea() or z.GetNetname() != "GND" or not z.IsOnLayer(layer):
        continue
    poly = z.GetFilledPolysList(layer)
    for i in range(poly.OutlineCount()):
        ch = poly.Outline(i)
        islands.append(((layer, i), GLYPHS[len(islands) % len(GLYPHS)], poly, ch, ch.BBox()))

print("ground islands on this layer:")
for key, g, _p, ch, bb in islands:
    print("   %s = %s  area=%7.2f mm2  bbox=(%.2f,%.2f)-(%.2f,%.2f)"
          % (g, key, abs(ch.Area()) / 1e12, TO(bb.GetLeft()), TO(bb.GetTop()),
             TO(bb.GetRight()), TO(bb.GetBottom())))
print()


def island_char(x, y):
    v = vec(x, y)
    for key, g, poly, ch, bb in islands:
        if not (TO(bb.GetLeft()) <= x <= TO(bb.GetRight())
                and TO(bb.GetTop()) <= y <= TO(bb.GetBottom())):
            continue
        if poly.Contains(v) and ch.PointInside(v):
            return g
    return None


# -- everything else on this layer ----------------------------------------
def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - (ax + u * dx)) ** 2 + (py - (ay + u * dy)) ** 2) ** 0.5


segs = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != layer:
        continue
    s, e = t.GetStart(), t.GetEnd()
    segs.append((t.GetNetname(), TO(s.x), TO(s.y), TO(e.x), TO(e.y), TO(t.GetWidth()) / 2.0))

vias = []
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        continue
    s = t.GetStart()
    try:
        r = TO(t.GetWidth(layer)) / 2.0
    except Exception:
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2.0
    vias.append((t.GetNetname(), TO(s.x), TO(s.y), r))

pads = []
for f in board.GetFootprints():
    for p in f.Pads():
        if not p.IsOnLayer(layer):
            continue
        o = p.GetPosition()
        bb = p.GetBoundingBox()
        pads.append((p.GetNetname(), f.GetReference(), str(p.GetNumber()),
                     TO(o.x), TO(o.y), bb))

NETPOOL = "abcdefghijklmnopqrstuvwxyz0123456789!@$%&?~#^"
legend = {}
for name, *_ in segs + vias + pads:
    if name and name not in legend:
        legend[name] = NETPOOL[len(legend) % len(NETPOOL)]
print("net glyphs:")
for k in sorted(legend, key=lambda n: legend[n]):
    print("   %s = %s" % (legend[k], k))
print()

nx = int((x2 - x1) / a.cell) + 1
ny = int((y2 - y1) / a.cell) + 1

print("      " + "".join("%-10s" % ("%.0f" % (x1 + i * a.cell)) if i % 40 == 0 else ""
                         for i in range((nx + 39) // 40)))
for j in range(ny):
    cy = y1 + j * a.cell
    row = []
    for i in range(nx):
        cx = x1 + i * a.cell
        c = island_char(cx, cy)
        if c:
            row.append(c)
            continue
        hit = None
        for (net, ax, ay, bx, by, hw) in segs:
            if seg_dist(cx, cy, ax, ay, bx, by) <= hw + a.cell * 0.4:
                hit = net
                break
        if hit is None:
            for (net, ref, num, px, py, bb) in pads:
                if (TO(bb.GetLeft()) - a.cell * 0.3 <= cx <= TO(bb.GetRight()) + a.cell * 0.3
                        and TO(bb.GetTop()) - a.cell * 0.3 <= cy <= TO(bb.GetBottom()) + a.cell * 0.3):
                    hit = net
                    break
        if hit is None:
            for (net, vx, vy, r) in vias:
                if (cx - vx) ** 2 + (cy - vy) ** 2 <= (r + a.cell * 0.4) ** 2:
                    hit = net
                    break
        row.append(legend.get(hit, "*") if hit else ".")
    print("%6.1f" % cy + "".join(row))
