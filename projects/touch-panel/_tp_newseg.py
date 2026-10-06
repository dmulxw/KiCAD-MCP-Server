"""What the router's 188 new segments are, and on which layer."""
import pcbnew
from collections import Counter

SRC = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
DST = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\_nospine.kicad_pcb"
TO = pcbnew.ToMM


def segs(p):
    b = pcbnew.LoadBoard(p)
    out = []
    for t in b.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        s, e = t.GetStart(), t.GetEnd()
        out.append((t.GetLayerName(), t.GetNetname(), round(TO(s.x), 3), round(TO(s.y), 3),
                    round(TO(e.x), 3), round(TO(e.y), 3)))
    return out


a, b = segs(SRC), segs(DST)
sa, sb = set(a), set(b)
new = [s for s in b if s not in sa]
gone = [s for s in a if s not in sb]

print("new segments: %d   removed: %d" % (len(new), len(gone)))
print("\nnew by layer:", dict(Counter(s[0] for s in new)))
print("removed by layer:", dict(Counter(s[0] for s in gone)))
print("\nnew by net:", dict(Counter(s[1] for s in new).most_common()))
print("removed by net:", dict(Counter(s[1] for s in gone).most_common()))

xs = [s[2] for s in new] + [s[4] for s in new]
print("\nnew segment x range: %.3f .. %.3f" % (min(xs), max(xs)))
ys = [s[3] for s in new] + [s[5] for s in new]
print("new segment y range: %.3f .. %.3f" % (min(ys), max(ys)))

print("\n=== 25 new B.Cu segments ===")
for s in [x for x in new if x[0] == "B.Cu"][:25]:
    print("   %-8s (%8.3f,%8.3f) -> (%8.3f,%8.3f)" % (s[1], s[2], s[3], s[4], s[5]))

print("\n=== 25 new F.Cu segments ===")
for s in [x for x in new if x[0] == "F.Cu"][:25]:
    print("   %-8s (%8.3f,%8.3f) -> (%8.3f,%8.3f)" % (s[1], s[2], s[3], s[4], s[5]))
