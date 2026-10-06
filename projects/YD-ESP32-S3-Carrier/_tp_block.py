"""Which items wall off a point?  Print everything within r of it.

The ASCII flood shows ROW16's corridor stopping dead at y=243.75 against a
wall that spans the whole window, on F.Cu, from 243.85 to 245.15.  A wall that
wide and flat is a horizontal track (or a run of them) plus keep-out.  Printing
the items near a point on the far side of it names the owner and its geometry
in one shot, which is what the patch has to be designed against.
"""
import os
import sys

import pcbnew

S = 1e6
PX = float(os.environ.get("TP_PX", "133.75"))
PY = float(os.environ.get("TP_PY", "244.50"))
R = float(os.environ.get("TP_R", "0.80"))
LAY = os.environ.get("TP_LAYER", "F")
BOARD = os.environ.get("TP_BOARD", "../touch-panel/touch-panel.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard(%s) returned None" % BOARD)

keep_alive = []
if os.environ.get("TP_DROP_J1"):
    gone = [f for f in board.GetFootprints() if f.GetReference() == "J1"]
    for f in gone:
        board.Remove(f)
    keep_alive.extend(gone)

want = pcbnew.F_Cu if LAY.upper().startswith("F") else pcbnew.B_Cu
print("items within %.2fmm of (%.3f, %.3f) on %s"
      % (R, PX, PY, "F.Cu" if want == pcbnew.F_Cu else "B.Cu"))


def seg_dist(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((PX - ax) * dx + (PY - ay) * dy) / L2))
    return ((PX - (ax + t * dx)) ** 2 + (PY - (ay + t * dy)) ** 2) ** 0.5


rows = []
for t in board.GetTracks():
    if not t.IsOnLayer(want):
        continue
    a, b2 = t.GetStart(), t.GetEnd()
    ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
    bx, by = pcbnew.ToMM(b2.x), pcbnew.ToMM(b2.y)
    # PCB_VIA has no single width: it is sized per layer (or by its drill), and
    # asking without a layer trips a KiCad assert.  A via blocks both layers at
    # its full diameter, which is the point of measuring it here.
    if t.GetClass() == "PCB_VIA":
        w = pcbnew.ToMM(t.GetWidth(want))
        kind = "via"
    else:
        w = pcbnew.ToMM(t.GetWidth())
        kind = "track"
    d = seg_dist(ax, ay, bx, by) - w / 2.0
    if d < R:
        rows.append((d, kind, t.GetNetname() or "--", w, ax, ay, bx, by))

for f in board.GetFootprints():
    for p in f.Pads():
        if not p.IsOnLayer(want):
            continue
        c = p.GetPosition()
        cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
        hw, hh = pcbnew.ToMM(p.GetSizeX()) / 2.0, pcbnew.ToMM(p.GetSizeY()) / 2.0
        dx = max(abs(PX - cx) - hw, 0.0)
        dy = max(abs(PY - cy) - hh, 0.0)
        d = (dx * dx + dy * dy) ** 0.5
        if d < R:
            rows.append((d, "pad %s.%s" % (f.GetReference(), p.GetNumber()),
                         p.GetNetname() or "--", 0.0, cx, cy, cx, cy))

rows.sort()
if not rows:
    print("  (nothing -- the point is free on this layer)")
for d, kind, net, w, ax, ay, bx, by in rows:
    print("  %6.3fmm  %-6s %-6s w%.3f  (%8.3f, %8.3f) -> (%8.3f, %8.3f)"
          % (d, net, kind, w, ax, ay, bx, by))
