"""Every filled-polygon vertex sits `clearance` away from the copper that
pushed it there.  So the vertices bounding the empty pocket name the blocker:
take the pocket's boundary points and find the nearest board item to each."""
import math
import collections

import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM

# pocket under the dev board
X0, Y0, X1, Y1 = 11.0, 14.0, 39.0, 36.0

def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0.0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

items = []           # (label, bbox(as x0,y0,x1,y1), nearest-distance function)
for fp in b.GetFootprints():
    ref = str(fp.GetReference())
    for p in fp.Pads():
        pos, sz = p.GetPosition(), p.GetSize()
        cx, cy = mm(pos.x), mm(pos.y)
        hw, hh = mm(sz.x) / 2.0, mm(sz.y) / 2.0

        def pd(px, py, cx=cx, cy=cy, hw=hw, hh=hh):
            dx = max(abs(px - cx) - hw, 0.0)
            dy = max(abs(py - cy) - hh, 0.0)
            return math.hypot(dx, dy)
        items.append((f"pad {ref}.{p.GetNumber()} net={p.GetNetname() or '-'} "
                      f"@({cx:.2f},{cy:.2f}) {mm(sz.x):.2f}x{mm(sz.y):.2f}", pd))
    bb = fp.GetBoundingBox(False, False)
    fb = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
    def fd(px, py, fb=fb):
        dx = max(fb[0] - px, px - fb[2], 0.0)
        dy = max(fb[1] - py, py - fb[3], 0.0)
        return math.hypot(dx, dy)
    items.append((f"<body {ref} x {fb[0]:.2f}..{fb[2]:.2f} y {fb[1]:.2f}..{fb[3]:.2f}>", fd))

for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
    hw = mm(t.GetWidth(pcbnew.F_Cu)) / 2.0 if t.GetClass() == "PCB_VIA" else mm(t.GetWidth()) / 2.0
    kind = "via" if t.GetClass() == "PCB_VIA" else "trk"
    def td(px, py, x1=x1, y1=y1, x2=x2, y2=y2, hw=hw):
        return max(seg_dist(px, py, x1, y1, x2, y2) - hw, 0.0)
    items.append((f"{kind} {t.GetNetname() or '-'} ({x1:.2f},{y1:.2f})-({x2:.2f},{y2:.2f}) w{2*hw:.2f}", td))

for d in b.Drawings():
    try:
        lay = str(d.GetLayerName())
    except Exception:
        lay = "?"
    if lay not in ("F.Cu", "B.Cu"):
        continue
    bb = d.GetBoundingBox()
    fb = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
    def dd(px, py, fb=fb):
        dx = max(fb[0] - px, px - fb[2], 0.0)
        dy = max(fb[1] - py, py - fb[3], 0.0)
        return math.hypot(dx, dy)
    items.append((f"<drawing {lay} {d.GetClass()} x {fb[0]:.2f}..{fb[2]:.2f} y {fb[1]:.2f}..{fb[3]:.2f}>", dd))

print(f"{len(items)} candidate items", flush=True)

z = [zz for zz in b.Zones()
     if not zz.GetIsRuleArea() and zz.GetLayer() == pcbnew.F_Cu][0]
poly = z.GetFilledPolysList(pcbnew.F_Cu)
ol = poly.Outline(0)
pts = []
for i in range(ol.PointCount()):
    p = ol.CPoint(i)
    x, y = mm(p.x), mm(p.y)
    if X0 <= x <= X1 and Y0 <= y <= Y1:
        pts.append((x, y))
print(f"{len(pts)} boundary vertices inside the pocket window", flush=True)

tally = collections.Counter()
for (x, y) in pts:
    best, bl = 1e9, None
    for lbl, fn in items:
        v = fn(x, y)
        if v < best:
            best, bl = v, lbl
    tally[(bl, round(best, 2))] += 1

for (lbl, d), n in tally.most_common(25):
    print(f"{n:5d}  at {d:5.2f} mm   {lbl}", flush=True)
