"""What copper surrounds a point, on which layer, at what distance."""
import sys, math
import pcbnew
BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
TO = pcbnew.ToMM
px, py, rad = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
board = pcbnew.LoadBoard(BOARD)
F_CU, B_CU = pcbnew.F_Cu, pcbnew.B_Cu
LN = {F_CU: "F", B_CU: "B"}

def sd(px, py, ax, ay, bx, by):
    dx, dy = bx-ax, by-ay
    L2 = dx*dx+dy*dy
    if L2 <= 1e-12: return math.hypot(px-ax, py-ay)
    u = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy)/L2))
    return math.hypot(px-(ax+u*dx), py-(ay+u*dy))

print("=== tracks/vias within %.2f of (%.3f,%.3f) ===" % (rad, px, py))
rows = []
for t in board.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if isinstance(t, pcbnew.PCB_VIA):
        d = math.hypot(px-ax, py-ay); w = TO(t.GetWidth(F_CU)); L = "TB"
    else:
        d = sd(px, py, ax, ay, bx, by); w = TO(t.GetWidth()); L = LN.get(t.GetLayer(), "?")
    if d <= rad:
        rows.append((d, t.GetNetname(), L, w, ax, ay, bx, by))
for r in sorted(rows):
    print("  d=%.3f %-10s %-2s w=%.2f  (%.3f,%.3f)->(%.3f,%.3f)" % r)

print("\n=== pads within %.2f ===" % rad)
for f in board.GetFootprints():
    for p in f.Pads():
        o = p.GetPosition()
        x, y = TO(o.x), TO(o.y)
        bb = p.GetBoundingBox()
        l, t, rr, b = TO(bb.GetLeft()), TO(bb.GetTop()), TO(bb.GetRight()), TO(bb.GetBottom())
        dx = max(l-px, 0, px-rr); dy = max(t-py, 0, py-b)
        d = math.hypot(dx, dy)
        if d <= rad:
            print("  d=%.3f %-10s %s.%s [%s] bbox=(%.3f,%.3f)-(%.3f,%.3f)"
                  % (d, p.GetNetname(), f.GetReference(), p.GetNumber(),
                     LN.get(p.GetLayer(), "?"), l, t, rr, b))
