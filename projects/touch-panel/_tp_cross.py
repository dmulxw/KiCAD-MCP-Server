"""List every track that crosses a vertical line, in y order."""
import sys, math
import pcbnew
BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
TO = pcbnew.ToMM
X = float(sys.argv[1]); y1 = float(sys.argv[2]); y2 = float(sys.argv[3])
board = pcbnew.LoadBoard(BOARD)
LN = {pcbnew.F_Cu: "F", pcbnew.B_Cu: "B"}
rows = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        if abs(TO(s.x) - X) < 0.5 and y1 <= TO(s.y) <= y2:
            rows.append((TO(s.y), "VIA", t.GetNetname(), TO(s.x), TO(s.y), "", ""))
        continue
    s, e = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if (ax - X) * (bx - X) > 0:
        continue
    if abs(bx - ax) < 1e-9:
        yy = ay
    else:
        u = (X - ax) / (bx - ax)
        yy = ay + u * (by - ay)
    if y1 <= yy <= y2:
        rows.append((yy, "TRK", t.GetNetname(), ax, ay, "%.2f,%.2f" % (bx, by),
                     str(LN.get(t.GetLayer(), "?"))))
print("tracks/vias crossing x=%.2f between y=%.1f and y=%.1f:" % (X, y1, y2))
for r in sorted(rows):
    print("  y=%7.3f  %-4s %-9s  (%8.3f,%8.3f) -> %-16s %s"
          % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))
