"""Dump one net's copper: vias first, then each layer's segments by length.

  python _probe_net.py IO10
"""
import sys
import pcbnew

BOARD = sys.argv[1]
NET = sys.argv[2]

b = pcbnew.LoadBoard(BOARD)
vias, segs = [], []
for t in b.GetTracks():
    if t.GetNetname() != NET:
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        s = t.GetStart()
        vias.append((pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))))
    else:
        a, c = t.GetStart(), t.GetEnd()
        segs.append((pcbnew.LayerName(t.GetLayer()),
                     pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                     pcbnew.ToMM(c.x), pcbnew.ToMM(c.y),
                     pcbnew.ToMM(t.GetWidth())))

print("=== %s: %d via(s), %d segment(s) ===" % (NET, len(vias), len(segs)))
for x, y, w in sorted(vias, key=lambda v: v[0]):
    print("  VIA  (%7.3f, %7.3f)  d=%.2f" % (x, y, w))

for lay in ("F.Cu", "B.Cu"):
    sel = [s for s in segs if s[0] == lay]
    tot = sum(((s[3] - s[1]) ** 2 + (s[4] - s[2]) ** 2) ** 0.5 for s in sel)
    print("\n  %s: %d seg(s), %.1f mm" % (lay, len(sel), tot))
    for _, x1, y1, x2, y2, w in sorted(sel, key=lambda s: -((s[3]-s[1])**2 + (s[4]-s[2])**2)):
        print("     (%7.3f, %7.3f) -> (%7.3f, %7.3f)  w=%.2f" % (x1, y1, x2, y2, w))
