"""The old row/column feeder copper, isolated by geometry.

J1 keeps its footprint but loses its row/column nets: pads 1-31 go to
IO9..IO12 and GND.  Any ROW*/CSEL* copper still reaching those pads would
short a row to ground, so it has to be identified and removed -- but the row
lines themselves must survive.

Print, per net, the tracks that come within YMIN of the connector, so the
feeder can be separated from the matrix it feeds.

  python _tp_feed.py [--ymin 232] [--min 0.5]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
J1Y = 243.15

argv = sys.argv[1:]
YMIN = float(argv[argv.index("--ymin") + 1]) if "--ymin" in argv else 232.0
MIN = float(argv[argv.index("--min") + 1]) if "--min" in argv else 0.5

b = pcbnew.LoadBoard(PCB)

nets = {}
for t in b.GetTracks():
    nm = t.GetNetname().lstrip("/")
    if not (nm.startswith("ROW") or nm.startswith("CSEL")):
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        nets.setdefault(nm, []).append(
            ("via", b.GetLayerName(t.GetLayer()),
             pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        continue
    s, e = t.GetStart(), t.GetEnd()
    nets.setdefault(nm, []).append(
        (b.GetLayerName(t.GetLayer()), pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
         pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)))


def k(n):
    return (0, int(n[3:])) if n.startswith("ROW") else (1, int(n[4:]))


for nm in sorted(nets, key=k):
    low = [s for s in nets[nm]
           if max(s[2], s[4]) > YMIN]
    if not low:
        print("%-8s  (nothing below y %.1f)" % (nm, YMIN))
        continue
    print("%-8s  %d of %d track(s) reach y>%.1f" % (nm, len(low), len(nets[nm]), YMIN))
    for lay, x0, y0, x1, y1 in sorted(low, key=lambda s: -max(s[2], s[4]))[:6]:
        if lay == "via":
            print("      via  (%.2f, %.2f)" % (x0, y0))
        else:
            print("      %-3s (%7.2f,%7.2f) -> (%7.2f,%7.2f)  dy %s"
                  % (lay, x0, y0, x1, y1,
                     "V" if abs(y1 - y0) > abs(x1 - x0) else "H"))
