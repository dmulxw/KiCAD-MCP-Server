"""What copper is at a coordinate?"""
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
X = float(sys.argv[1]); Y = float(sys.argv[2]); R = float(sys.argv[3])

board = pcbnew.LoadBoard(HERE + r"\touch-panel.kicad_pcb")
print("board tracks: %d" % len(list(board.GetTracks())))


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return ((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2) ** 0.5


print("\n--- tracks/vias within %.2f mm of (%.2f, %.2f) ---" % (R, X, Y))
for t in board.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    x1, y1 = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
    x2, y2 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
    d = seg_dist(X, Y, x1, y1, x2, y2)
    if d <= R:
        kind = "VIA " if isinstance(t, pcbnew.PCB_VIA) else "SEG "
        print("  %s net=%-10s L=%-6s w=%.2f  (%.2f,%.2f)-(%.2f,%.2f)  d=%.2f"
              % (kind, t.GetNetname(), board.GetLayerName(t.GetLayer()),
                 pcbnew.ToMM(t.GetWidth()), x1, y1, x2, y2, d))

print("\n--- pads within %.2f mm ---" % R)
for fp in board.GetFootprints():
    for p in fp.Pads():
        pos = p.GetPosition()
        px, py = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        d = ((px - X) ** 2 + (py - Y) ** 2) ** 0.5
        if d <= R:
            sz = p.GetSize()
            print("  PAD %s.%s net=%-10s L=%-6s %.2fx%.2f  (%.2f,%.2f) d=%.2f"
                  % (fp.GetReference(), p.GetNumber(), p.GetNetname(),
                     board.GetLayerName(p.GetLayer()),
                     pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y), px, py, d))
