"""Full inventory of the wall band, both layers, grouped by net.

  python _tp_band.py [X1] [X2]
"""
import sys
from collections import defaultdict
import pcbnew
BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X1 = float(sys.argv[1]) if len(sys.argv) > 1 else 99.4
X2 = float(sys.argv[2]) if len(sys.argv) > 2 else 105.2

board = pcbnew.LoadBoard(BOARD)
by = defaultdict(lambda: defaultdict(list))
for t in board.GetTracks():
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by_ = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    if isinstance(t, pcbnew.PCB_VIA):
        if not (X1 <= ax <= X2):
            continue
        d = TO(t.GetDrill())
        by[t.GetNetname()]["via"].append((ay, ay, ax, ay, ax, ay, TO(t.GetWidth(pcbnew.F_Cu))))
        continue
    l = t.GetLayer()
    if l not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    w = TO(t.GetWidth())
    if max(ax, bx) + w / 2 < X1 or min(ax, bx) - w / 2 > X2:
        continue
    ln = "F" if l == pcbnew.F_Cu else "B"
    by[t.GetNetname()][ln].append((min(ay, by_) - w / 2, max(ay, by_) + w / 2,
                                   ax, ay, bx, by_, w))

for net in sorted(by, key=lambda n: -sum(len(v) for v in by[n].values())):
    tot = sum(len(v) for v in by[net].values())
    kinds = ",".join("%s=%d" % (k, len(v)) for k, v in sorted(by[net].items()))
    print("\n%-9s %3d piece(s)  [%s]" % (net, tot, kinds))
    for ln in ("F", "B", "via"):
        if ln not in by[net]:
            continue
        for (s, e, ax, ay, bx, by_, w) in sorted(by[net][ln]):
            if ln == "via":
                print("   via      (%8.3f,%8.3f) pad=%.2f" % (ax, ay, w))
            else:
                print("   %s   y %7.2f..%7.2f  (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f"
                      % (ln, s, e, ax, ay, bx, by_, w))
