"""Every copper item with any part inside a mm box, grouped by layer."""
import sys
from collections import defaultdict
import pcbnew
S = 1e6
b = pcbnew.LoadBoard(sys.argv[1])
X0, Y0, X1, Y1 = (float(v) for v in sys.argv[2:6])
rows = []
for t in b.GetTracks():
    via = isinstance(t, pcbnew.PCB_VIA)
    if via:
        bb = t.GetBoundingBox()
        ax, ay, bx, by = bb.GetLeft()/S, bb.GetTop()/S, bb.GetRight()/S, bb.GetBottom()/S
        lay = "ALL"
    else:
        s, e = t.GetStart(), t.GetEnd()
        ax, ay, bx, by = min(s.x,e.x)/S, min(s.y,e.y)/S, max(s.x,e.x)/S, max(s.y,e.y)/S
        lay = b.GetLayerName(t.GetLayer())
    if bx < X0 or ax > X1 or by < Y0 or ay > Y1:
        continue
    rows.append(("via" if via else "trk", lay, t.GetNetname(),
                 s.x/S if not via else ax, s.y/S if not via else ay,
                 e.x/S if not via else bx, e.y/S if not via else by,
                 t.GetWidth()/S if not via else 0))
print(f"box ({X0},{Y0})-({X1},{Y1}): {len(rows)} item(s)")
byside = defaultdict(list)
for r in rows: byside[r[1]].append(r)
for lay in sorted(byside):
    print(f"\n--- {lay} ({len(byside[lay])}) ---")
    for k, l, n, x0, y0, x1, y1, w in sorted(byside[lay], key=lambda r: (r[3], r[2])):
        if k == "via":
            print(f"  via {n:<8} @({x0:8.3f},{y0:8.3f})")
        else:
            print(f"  trk {n:<8} ({x0:8.3f},{y0:8.3f})->({x1:8.3f},{y1:8.3f}) w{w:.3f}")
