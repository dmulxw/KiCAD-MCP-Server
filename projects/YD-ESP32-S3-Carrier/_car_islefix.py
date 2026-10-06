"""Tie off GND pour islands that no copper reaches.

The pour closed 67 of the 70 GND gaps.  Three B.Cu islands stay floating:
no GND via, pad or track sits inside them, so nothing connects them to the
plane and DRC lists each as unconnected.  (Every F.Cu island already holds a
via, and B.Cu has one large contiguous body, so these three are the whole
problem.)

The repair is one GND stitching via per island, but the landing point has to
satisfy two things at once.  The via must sit inside the B.Cu island -- that is
what ties the island down -- and it must also sit inside F.Cu GND copper, or
its other end lands on bare board and the island stays isolated anyway.

A disc test rather than a point test settles both: for a candidate to count,
eight points on the via's circumference must lie inside the copper on each
layer.  That also handles clearance for free.  An island's edge is by
construction already CLEAR away from every other net, so a disc that stays
inside the island cannot touch anything else, and no separate collision scan
is needed.

Islands where no such point exists are reported and left alone rather than
guessed at.

  python _car_islefix.py --dry
  python _car_islefix.py
"""
import math
import os
import shutil
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = os.path.join(HERE, "YD-ESP32-S3-Carrier.kicad_pcb")
BACKUP = BOARD + ".pre-islefix.bak"
DRY = "--dry" in sys.argv

VIA_D = 0.60
VIA_DRILL = 0.30
MARGIN = 0.05          # extra room beyond the via radius
STEP = 0.10            # candidate grid inside each island

board = pcbnew.LoadBoard(BOARD)
TO = pcbnew.ToMM

gnd = board.FindNet("GND")
netcode = gnd.GetNetCode() if gnd is not None else 0

polys = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}
for z in board.Zones():
    if z.GetIsRuleArea() or z.GetNetname() != "GND":
        continue
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        if z.IsOnLayer(layer):
            polys[layer].append((z, z.GetFilledPolysList(layer)))

pts = []
for t in board.GetTracks():
    if t.GetNetname() != "GND":
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        pts.append((TO(s.x), TO(s.y)))
    else:
        for e in (t.GetStart(), t.GetEnd()):
            pts.append((TO(e.x), TO(e.y)))
for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNetname() == "GND":
            o = p.GetPosition()
            pts.append((TO(o.x), TO(o.y)))

R = VIA_D / 2.0 + MARGIN
ANGLES = [(math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)) for a in range(8)]


def disc_inside(cands, x, y):
    for _, poly in cands:
        if not poly.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))):
            continue
        ok = True
        for dx, dy in ANGLES:
            q = pcbnew.VECTOR2I(pcbnew.FromMM(x + R * dx), pcbnew.FromMM(y + R * dy))
            if not poly.Contains(q):
                ok = False
                break
        if ok:
            return True
    return False


def find_point(chain, bbox):
    x0, y0 = TO(bbox.GetLeft()), TO(bbox.GetTop())
    x1, y1 = TO(bbox.GetRight()), TO(bbox.GetBottom())
    nx = max(1, int((x1 - x0) / STEP))
    ny = max(1, int((y1 - y0) / STEP))
    best = None
    for i in range(nx + 1):
        for j in range(ny + 1):
            x = x0 + i * STEP
            y = y0 + j * STEP
            v = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
            if not chain.PointInside(v):
                continue
            if any(abs(x - px) < 0.30 and abs(y - py) < 0.30 for px, py in pts):
                continue
            if disc_inside(polys[pcbnew.F_Cu], x, y) and disc_inside(polys[pcbnew.B_Cu], x, y):
                # prefer the most central landing spot
                d = min(abs(x - x0), abs(x1 - x), abs(y - y0), abs(y1 - y))
                if best is None or d > best[0]:
                    best = (d, x, y)
    return None if best is None else (best[1], best[2])


plan = []
for z, poly in polys[pcbnew.B_Cu]:
    for i in range(poly.OutlineCount()):
        chain = poly.Outline(i)
        bb = chain.BBox()
        # Count the GND items inside directly.  An earlier version seeded this
        # from the bbox centre and skipped the count when that centre was not
        # interior -- which is exactly the main plane, whose centre falls in a
        # hole, so the whole plane was reported as floating.
        hits = 0
        for (x, y) in pts:
            v = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
            if poly.Contains(v) and chain.PointInside(v):
                hits += 1
        if hits:
            continue
        area = abs(chain.Area()) / 1e12
        spot = find_point(chain, bb)
        plan.append((i, area, bb, spot))

print("floating B.Cu island(s): %d" % len(plan))
for i, area, bb, spot in plan:
    print("   [%2d] area=%7.3f mm2 bbox=(%.2f,%.2f)-(%.2f,%.2f)  via=%s"
          % (i, area, TO(bb.GetLeft()), TO(bb.GetTop()), TO(bb.GetRight()),
             TO(bb.GetBottom()),
             ("(%.3f,%.3f)" % spot) if spot else "NO FREE SPOT"))

todo = [p for p in plan if p[3]]
if not todo:
    print("\nnothing to place")
    sys.exit(0)
if DRY:
    print("\ndry run -- nothing written")
    sys.exit(0)

shutil.copyfile(BOARD, BACKUP)
print("\nbackup -> %s" % BACKUP)

for i, area, bb, (x, y) in todo:
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetWidth(pcbnew.FromMM(VIA_D))
    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    v.SetNetCode(netcode)
    board.Add(v)
    print("   + GND via at (%.3f,%.3f)" % (x, y))

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(BOARD)
print("saved: %d via(s), zones refilled" % len(todo))
