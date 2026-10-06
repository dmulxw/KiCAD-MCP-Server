"""Is x 98.4..100.3 clear on F.Cu, and what sits in the strip west of the spine?

The spine is the R pad-2 ground bus.  Moving it west out of the wall only works
if the strip it moves into is empty for the whole board height, so list every
F.Cu track that intrudes on that strip, and separately every GND piece there.
"""
import sys, pcbnew
BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X1, X2 = float(sys.argv[1]), float(sys.argv[2])
board = pcbnew.LoadBoard(BOARD)

rows = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.F_Cu:
        continue
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    w = TO(t.GetWidth())
    if max(ax, bx) + w / 2 < X1 or min(ax, bx) - w / 2 > X2:
        continue
    rows.append((min(ay, by) - w / 2, max(ay, by) + w / 2, t.GetNetname(),
                 ax, ay, bx, by, w))
rows.sort()
print("F.Cu tracks intersecting x %.2f..%.2f : %d" % (X1, X2, len(rows)))
prev_e = None
for (s, e, n, ax, ay, bx, by, w) in rows:
    mark = ""
    if prev_e is not None and s - prev_e > 0.62:
        mark = "   <== FREE Y-GAP %.2f mm" % (s - prev_e)
    prev_e = e if prev_e is None else max(prev_e, e)
    print("  y %7.2f..%7.2f  %-9s (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f%s"
          % (s, e, n, ax, ay, bx, by, w, mark))
print("\nby net:")
from collections import Counter
for n, c in Counter(r[2] for r in rows).most_common():
    print("   %-9s %d piece(s)" % (n, c))
