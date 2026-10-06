"""For each failed net, where are its pads, and what is the failing pad near?"""
import collections, math
import pcbnew
BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
TO = pcbnew.ToMM
board = pcbnew.LoadBoard(BOARD)

pads = collections.defaultdict(list)
for f in board.GetFootprints():
    for p in f.Pads():
        n = p.GetNetname()
        if not n: continue
        o = p.GetPosition()
        pads[n].append((f.GetReference(), str(p.GetNumber()), TO(o.x), TO(o.y)))
for n in sorted(pads):
    if not (n.startswith("ROW") or n.startswith("CSEL") or n in ("+3V3","IO9","IO10","IO11","IO12","GND","DRV_CASC1","DRV_CASC2","DRV_CASC3")):
        continue
    v = pads[n]
    print("%-10s %2d pad(s)" % (n, len(v)))
    for (r,num,x,y) in sorted(v, key=lambda e:(e[2],e[3])):
        print("      %-5s %-3s (%8.3f,%8.3f)" % (r,num,x,y))
