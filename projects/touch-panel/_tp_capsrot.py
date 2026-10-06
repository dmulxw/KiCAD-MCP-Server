"""Test: does standing the four decoupling caps upright free the west strip?

Measured facts this acts on:
  * the 595 control pins are all on x=92.72 (pads 9-16, west column); pads 1-8
    are east at x=97.67
  * IO10/IO11/IO12 and +3V3 need a vertical each, y 171..241, in the strip west
    of the pad column
  * that strip holds legal track centres x 90.55..91.45 (0.90 mm = 3 lanes at
    0.4 mm pitch) but only x 90.55..90.75 is free for the whole span
  * the blockers are CSEL3 on B.Cu (westmost copper 91.050) and the caps' GND
    pads at x 91.240..91.800

C1..C4 sit horizontally at (92.00, 180.50/200.50/220.50/240.50), body 1.87 wide
x 0.97 tall, so their pads straddle the strip.  Standing them upright moves both
pads onto x ~92.00, letting the strip clear to x 91.45.

This writes a SCRATCH board (_capsv.kicad_pcb, with its .kicad_pro copied beside
it -- the design rules live in the project file, not the board) and reports:
the pads' new geometry, every foreign net the new pads would land on, and the
recomputed lane set.  touch-panel.kicad_pcb is never touched.

  python _tp_capsrot.py
"""
import shutil
from collections import defaultdict

import pcbnew

SRC = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
DST = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\_capsv.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
REFS = ("C1", "C2", "C3", "C4")
EDGE = 89.95
EDGE_CLR = 0.5
CLR = 0.2

board = pcbnew.LoadBoard(SRC)

# ---- stand the caps upright ------------------------------------------------
moved = []
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    if ref not in REFS:
        continue
    before = (fp.GetOrientationDegrees(), fp.GetPosition().x, fp.GetPosition().y)
    fp.SetOrientationDegrees((fp.GetOrientationDegrees() + 90) % 360)
    moved.append((ref, before, fp.GetOrientationDegrees()))
print("=== caps rotated to vertical (scratch board only) ===")
for (ref, before, ang) in moved:
    print("  %-3s  %.0f deg -> %.0f deg" % (ref, before[0], ang))

# ---- what do the new pads land on? -----------------------------------------
print("\n=== new pad geometry, and foreign copper underneath ===")
foreign = []
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    if ref not in REFS:
        continue
    q = fp.GetBoundingBox(False, False)
    print("  %s bbox x %.3f..%.3f  y %.3f..%.3f"
          % (ref, q.GetLeft() / S, q.GetRight() / S,
             q.GetTop() / S, q.GetBottom() / S))
    for p in fp.Pads():
        r = p.GetBoundingBox()
        lo, hi, t, b = (r.GetLeft() / S, r.GetRight() / S,
                        r.GetTop() / S, r.GetBottom() / S)
        pn = str(p.GetNetname())
        print("      pad %-2s %-6s x %.3f..%.3f  y %.3f..%.3f"
              % (str(p.GetNumber()), pn, lo, hi, t, b))
        for tr in board.GetTracks():
            if isinstance(tr, pcbnew.PCB_VIA):
                pos = tr.GetPosition()
                x, y = TO(pos.x), TO(pos.y)
                rr = TO(tr.GetWidth(pcbnew.F_Cu)) / 2
                bb = (x - rr, y - rr, x + rr, y + rr)
            else:
                s, e = tr.GetStart(), tr.GetEnd()
                x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
                w = TO(tr.GetWidth()) / 2
                bb = (min(x1, x2) - w, min(y1, y2) - w,
                      max(x1, x2) + w, max(y1, y2) + w)
            if bb[2] < lo or bb[0] > hi or bb[3] < t or bb[1] > b:
                continue
            if str(tr.GetNetname()) == pn:
                continue
            foreign.append((ref, str(p.GetNumber()), pn,
                            str(tr.GetNetname()), str(tr.GetLayerName()),
                            round(bb[0], 3), round(bb[1], 3)))
if foreign:
    f = defaultdict(int)
    for (ref, pad, pn, tn, lay, _x, _y) in foreign:
        f["%s.%s(%s) <- %s on %s @x%.2f" % (ref, pad, pn, tn, lay, _x)] += 1
    for k, v in sorted(f.items()):
        print("   COLLISION %s  x%d" % (k, v))
else:
    print("   no foreign copper under the rotated caps")

y, x = board.GetFootprints()[0].GetPosition().y, 0

# ---- recompute the lane set with the caps out of the way -------------------
obst = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        xx, yy = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        obst.append((xx - r, xx + r, yy - r, yy + r, "V"))
        continue
    if t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth()) / 2
    obst.append((min(x1, x2) - w, max(x1, x2) + w, min(y1, y2) - w,
                 max(y1, y2) + w, "F" if t.GetLayer() == pcbnew.F_Cu else "B"))
for fp in board.GetFootprints():
    for p in fp.Pads():
        q = p.GetBoundingBox()
        obst.append((q.GetLeft() / S, q.GetRight() / S,
                     q.GetTop() / S, q.GetBottom() / S, "P"))

Y0, Y1 = 168.0, 238.0
print("\n=== lane set over y %.0f..%.0f, per layer (x 90.45..91.90) ===" % (Y0, Y1))
for want in ("F", "B"):
    common = None
    yy = Y0
    died = None
    while yy <= Y1 + 1e-9:
        xs = set()
        k = 0
        while True:
            x = round(90.55 + k * 0.05, 3)
            if x > 91.90 + 1e-9:
                break
            bad = False
            for (l, r, t0, b, tag) in obst:
                if tag in ("V", "P") or tag == want:
                    if l - CLR - 0.1 <= x <= r + CLR + 0.1 and \
                       t0 - CLR - 0.1 <= yy <= b + CLR + 0.1:
                        bad = True
                        break
            if not bad:
                xs.add(x)
            k += 1
        common = xs if common is None else (common & xs)
        if not common and died is None:
            died = yy
        yy += 0.25
    lbl = "F.Cu" if want == "F" else "B.Cu"
    if common:
        runs, cur = [], [sorted(common)[0]]
        for x in sorted(common)[1:]:
            if abs(x - cur[-1] - 0.05) < 1e-6:
                cur.append(x)
            else:
                runs.append((cur[0], cur[-1]))
                cur = [x]
        runs.append((cur[0], cur[-1]))
        print("  %s: free for the WHOLE span at %s"
              % (lbl, ", ".join("%.2f..%.2f" % r for r in runs)))
    else:
        print("  %s: no x holds the whole span; lane set first emptied at y=%.2f"
              % (lbl, died))

# ---- save --------------------------------------------------------------
pcbnew.SaveBoard(DST, board)
shutil.copy(SRC[:-10] + ".kicad_pro", DST[:-10] + ".kicad_pro")
print("\nwrote %s (+ .kicad_pro)" % DST)
