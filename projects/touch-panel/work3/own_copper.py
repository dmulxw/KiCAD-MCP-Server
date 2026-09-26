"""Dump a net's own copper: tracks, vias, pads -- geometry and extent."""
import sys
import pcbnew
S = 1e6
b = pcbnew.LoadBoard(sys.argv[1])
name = sys.argv[2]
rows = []
for t in b.GetTracks():
    if t.GetNetname() != name:
        continue
    s, e = t.GetStart(), t.GetEnd()
    kind = "via" if isinstance(t, pcbnew.PCB_VIA) else "trk"
    lay = "ALL" if kind == "via" else b.GetLayerName(t.GetLayer())
    rows.append((kind, lay, s.x/S, s.y/S, e.x/S, e.y/S))
pads = []
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname() == name:
            bb = p.GetBoundingBox()
            pads.append((fp.GetReference(), p.GetNumber(),
                         bb.GetLeft()/S, bb.GetTop()/S, bb.GetRight()/S, bb.GetBottom()/S))
print(f"{name}: {len(rows)} track/via item(s), {len(pads)} pad(s)")
for k, l, x0, y0, x1, y1 in sorted(rows, key=lambda r: (r[1], r[3], r[2])):
    print(f"  {k:<3} {l:<5} ({x0:8.3f},{y0:8.3f}) -> ({x1:8.3f},{y1:8.3f})")
print("  pads:")
for ref, num, x0, y0, x1, y1 in sorted(pads, key=lambda r: (r[1], r[2])):
    print(f"    {ref}.{num:<4} x[{x0:8.3f},{x1:8.3f}] y[{y0:8.3f},{y1:8.3f}]")
