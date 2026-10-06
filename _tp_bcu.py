"""Everything on B.Cu inside the band, plus every via, so I know what moving the
three trunks west actually leaves behind.

  python _tp_bcu.py [X1] [X2]
"""
import sys
from collections import defaultdict
import pcbnew
BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X1 = float(sys.argv[1]) if len(sys.argv) > 1 else 99.9
X2 = float(sys.argv[2]) if len(sys.argv) > 2 else 102.2

board = pcbnew.LoadBoard(BOARD)
print("=== B.Cu tracks with any copper in x %.2f..%.2f ===" % (X1, X2))
rows = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.B_Cu:
        continue
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    w = TO(t.GetWidth())
    if max(ax, bx) + w / 2 < X1 or min(ax, bx) - w / 2 > X2:
        continue
    rows.append((min(ax, bx), max(ax, bx), min(ay, by), max(ay, by),
                 t.GetNetname(), ax, ay, bx, by, w))
for r in sorted(rows, key=lambda r: (r[2], r[0])):
    print("   %-9s x %8.3f..%8.3f  y %8.3f..%8.3f  (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f"
          % (r[4], r[0], r[1], r[2], r[3], r[5], r[6], r[7], r[8], r[9]))
print("   total %d" % len(rows))

print("\n=== B.Cu tracks in the DESTINATION strip x 98.4..100.0 ===")
dest = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.B_Cu:
        continue
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    w = TO(t.GetWidth())
    if max(ax, bx) + w / 2 < 98.4 or min(ax, bx) - w / 2 > 100.0:
        continue
    dest.append((min(ay, by), max(ay, by), t.GetNetname(), ax, ay, bx, by, w))
for r in sorted(dest):
    print("   %-9s y %8.3f..%8.3f  (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f"
          % (r[2], r[0], r[1], r[3], r[4], r[5], r[6], r[7]))
print("   total %d" % len(dest))

print("\n=== Vias inside x %.2f..%.2f ===" % (X1, X2))
v = []
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        continue
    p = t.GetPosition()
    x, y = TO(p.x), TO(p.y)
    if X1 <= x <= X2:
        v.append((y, x, t.GetNetname(), TO(t.GetWidth(pcbnew.F_Cu)), TO(t.GetDrill())))
for r in sorted(v):
    print("   %-9s (%8.3f,%8.3f) pad=%.2f drill=%.2f" % (r[2], r[1], r[0], r[3], r[4]))
print("   total %d" % len(v))
