"""Print every piece of copper belonging to the named nets.

The patch has to be designed against real geometry, and the geometry that
matters is the nets in the way -- not a keep-out grid, which flattens a via and
a trunk into the same number.  Print each net's tracks, vias and pads with
endpoints, sorted by layer then y then x, so a trunk's y and a stub's x can be
read off directly and a proposed detour can be checked by eye before any tool
runs.
"""
import os
import sys

import pcbnew

S = 1e6
NAMES = sys.argv[1:] or ["ROW16", "ROW17"]
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


def lname(lay):
    return {pcbnew.F_Cu: "F.Cu", pcbnew.B_Cu: "B.Cu"}.get(lay, str(lay))


for name in NAMES:
    print("\n=== %s ===" % name)
    rows = []
    for t in board.GetTracks():
        if t.GetNetname() != name:
            continue
        a, b2 = t.GetStart(), t.GetEnd()
        isvia = t.GetClass() == "PCB_VIA"
        if isvia:
            w = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))
        else:
            w = pcbnew.ToMM(t.GetWidth())
        rows.append((t.GetLayer() if not isvia else -1,
                     pcbnew.ToMM(a.y), pcbnew.ToMM(a.x),
                     "via " if isvia else "trk ",
                     pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                     pcbnew.ToMM(b2.x), pcbnew.ToMM(b2.y), w))
    for lay, ay, ax, kind, sx, sy, ex, ey, w in sorted(rows):
        L = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
        print("  %-5s %s w%.3f  (%9.3f, %9.3f) -> (%9.3f, %9.3f)  %.3f"
              % (lname(lay) if lay >= 0 else "both", kind, w, sx, sy, ex, ey, L))
    pn = 0
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() != name:
                continue
            c = p.GetPosition()
            print("  %-5s pad  %s.%s  (%9.3f, %9.3f)  %.2f x %.2f"
                  % (",".join(lname(l) for l in p.GetLayerSet().Seq()[:1]),
                     f.GetReference(), p.GetNumber(), pcbnew.ToMM(c.x),
                     pcbnew.ToMM(c.y), pcbnew.ToMM(p.GetSizeX()),
                     pcbnew.ToMM(p.GetSizeY())))
            pn += 1
    print("  %d track/via + %d pad" % (len(rows), pn))
