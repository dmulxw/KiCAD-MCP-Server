"""What exactly seals ROW16/ROW17 in?  Dump the copper in the window.

_tp_why.py says ROW16's usable free space stops at y=243.75 and ROW17's at the
same height, a quarter of a millimetre below where the strip begins, while
ROW18 and ROW19 next to them get through.  The difference is local, so the
patch has to be local, and a local patch needs the actual list of copper in the
window -- not an obstacle grid, which is what every measurement so far has
looked at.  Print every track and pad intersecting the window with its net,
layer, width and endpoints, sorted by x, so the fence can be read off directly.
"""
import os
import sys

import pcbnew

S = 1e6
X0, X1 = float(os.environ.get("TP_X0", "128")), float(os.environ.get("TP_X1", "141"))
Y0, Y1 = float(os.environ.get("TP_Y0", "239")), float(os.environ.get("TP_Y1", "252"))
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
    print("dropped %d footprint(s): J1" % len(gone))

EXT = float(os.environ.get("TP_EXTEND_DOWN", "0"))
if EXT:
    ys = [pt.y for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts
          for pt in (d.GetStart(), d.GetEnd())]
    YMAX = max(ys)
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        a, b2 = d.GetStart(), d.GetEnd()
        if abs(a.y - b2.y) < 1:
            continue
        for pt in (a, b2):
            if abs(pt.y - YMAX) < 1:
                pt.y = int(round(pt.y + EXT * S))
        d.SetStart(a)
        d.SetEnd(b2)


def name(lay):
    return {pcbnew.F_Cu: "F.Cu", pcbnew.B_Cu: "B.Cu"}.get(lay, str(lay))


def inside(v):
    x, y = pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)
    return X0 - 0.6 <= x <= X1 + 0.6 and Y0 - 0.6 <= y <= Y1 + 0.6


print("window x %.1f..%.1f  y %.1f..%.1f" % (X0, X1, Y0, Y1))
print("\n--- tracks ---")
print("  %-6s %-5s %-8s %-22s %-22s %s"
      % ("net", "layer", "width", "start", "end", "len"))
rows = []
for t in board.GetTracks():
    if pcbnew.ToMM(t.GetWidth()) < 0 and False:
        continue
    a, b2 = t.GetStart(), t.GetEnd()
    if not (inside(a) or inside(b2)):
        # also catch a segment that merely crosses the window
        ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
        bx, by = pcbnew.ToMM(b2.x), pcbnew.ToMM(b2.y)
        if not (min(ax, bx) <= X1 and max(ax, bx) >= X0
                and min(ay, by) <= Y1 and max(ay, by) >= Y0):
            continue
    L = ((pcbnew.ToMM(b2.x) - pcbnew.ToMM(a.x)) ** 2
         + (pcbnew.ToMM(b2.y) - pcbnew.ToMM(a.y)) ** 2) ** 0.5
    rows.append((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y), pcbnew.ToMM(b2.x),
                 pcbnew.ToMM(b2.y), t.GetNetname() or "--",
                 t.GetLayer(), pcbnew.ToMM(t.GetWidth()), L))

rows.sort()
for ax, ay, bx, by, net, lay, w, L in rows:
    print("  %-6s %-5s %8.3f  (%8.3f, %8.3f)  (%8.3f, %8.3f)  %.3f"
          % (net, name(lay), w, ax, ay, bx, by, L))

print("\n--- pads ---")
prow = []
for fp in board.GetFootprints():
    for p in fp.Pads():
        c = p.GetPosition()
        if not inside(c):
            continue
        x, y = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
        prow.append((x, y, fp.GetReference(), p.GetNumber(),
                     p.GetNetname() or "--",
                     pcbnew.ToMM(p.GetSizeX()), pcbnew.ToMM(p.GetSizeY()),
                     [name(l) for l in p.GetLayerSet().Seq()][:2]))
prow.sort()
for x, y, ref, num, net, sx, sy, lays in prow:
    print("  %-6s %-14s pad %-4s (%8.3f, %8.3f)  %.2f x %.2f  %s"
          % (net, ref, num, x, y, sx, sy, ",".join(lays)))

print("\n  %d tracks, %d pads in window" % (len(rows), len(prow)))
