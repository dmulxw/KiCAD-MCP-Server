"""Every piece of copper on CSEL4, ROW1 and ROW8, plus their pads.

Three long B.Cu verticals are what seal the west wall, and they are going to be
lifted and re-laid further west.  Before deleting anything I need to know what
else those three nets own -- the trunk is only useful if I can see which pieces
would be left dangling once it goes, and which of them are the detour work the
closed wall forced them into and can therefore go too.

  python _tp_three.py
"""
import sys
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
NETS = sys.argv[1:] or ["CSEL4", "ROW1", "ROW8"]

board = pcbnew.LoadBoard(BOARD)

for net in NETS:
    print("\n=== %s ===" % net)
    print("  pads:")
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() != net:
                continue
            o = p.GetPosition()
            pb = p.GetBoundingBox()
            print("    %-5s pad %-3s (%8.3f,%8.3f)  %.2f x %.2f  %s"
                  % (f.GetReference(), str(p.GetNumber()), TO(o.x), TO(o.y),
                     TO(pb.GetWidth()), TO(pb.GetHeight()),
                     board.GetLayerName(p.GetLayer())))

    tracks, vias = [], []
    for t in board.GetTracks():
        if t.GetNetname() != net:
            continue
        a, b = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
        if isinstance(t, pcbnew.PCB_VIA):
            vias.append((y1, x1, TO(t.GetWidth(pcbnew.F_Cu)), TO(t.GetDrill())))
        else:
            ln = "F" if t.GetLayer() == pcbnew.F_Cu else (
                "B" if t.GetLayer() == pcbnew.B_Cu else "?")
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            tracks.append((ln, y1, length, x1, y1, x2, y2, TO(t.GetWidth())))

    print("  tracks: %d" % len(tracks))
    for (ln, _s, length, x1, y1, x2, y2, w) in sorted(tracks):
        print("    %s  (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.2f  L=%7.2f" %
              (ln, x1, y1, x2, y2, w, length))
    print("  vias: %d" % len(vias))
    for (y, x, w, d) in sorted(vias):
        print("    (%8.3f,%8.3f) pad=%.2f drill=%.2f" % (x, y, w, d))

# Which nets own B.Cu copper anywhere in the band, tallied by total length, so I
# can see whether lifting the three is really enough or another net is hiding.
print("\n=== every net with B.Cu copper reaching into x 100.2..101.9 ===")
tally = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.B_Cu:
        continue
    a, b = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    w = TO(t.GetWidth())
    if max(x1, x2) + w / 2 < 100.2 or min(x1, x2) - w / 2 > 101.9:
        continue
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    r = tally[t.GetNetname()]
    r[0] += 1
    r[1] += length
    r[2] = min(r[2] or y1, y1)
    r[3] = max(r[3], y1, y2)
for n, (c, L, lo, hi) in sorted(tally.items(), key=lambda kv: -kv[1][1]):
    print("   %-9s %2d piece(s)  %7.1f mm   y %.1f..%.1f" % (n, c, L, lo, hi))
