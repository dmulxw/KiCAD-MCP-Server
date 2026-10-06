"""Which rectangles in the new strip are actually copper-free -- measured, not guessed.

Probe 1 used fp.GetBoundingBox(), which folds in the Reference/Value text and so
reports a 3.2mm mounting hole as a 19mm obstacle.  What matters for placement and
routing is PAD copper, so this reports the union of each footprint's pad boxes.
"""
import pcbnew

S = 1e6
YD = "YD-ESP32-S3-Carrier.kicad_pcb"
board = pcbnew.LoadBoard(YD)


def pad_box(fp):
    xs, ys = [], []
    for p in fp.Pads():
        b = p.GetBoundingBox()
        xs += [b.GetLeft() / S, b.GetRight() / S]
        ys += [b.GetTop() / S, b.GetBottom() / S]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


rows = []
for fp in board.GetFootprints():
    pb = pad_box(fp)
    if pb:
        rows.append((fp.GetReference(), pb, str(fp.GetFPID().GetLibItemName())))

print("-- footprint PAD extents (copper only) --")
for ref, pb, name in sorted(rows, key=lambda r: (r[1][1], r[1][0])):
    print("  %-7s x %6.2f..%6.2f  y %6.2f..%6.2f   %s"
          % (ref, pb[0], pb[2], pb[1], pb[3], name))


def hits(rect):
    x0, y0, x1, y1 = rect
    return sorted(ref for ref, pb, _ in rows
                  if not (pb[2] <= x0 or pb[0] >= x1 or pb[3] <= y0 or pb[1] >= y1))


print()
print("-- candidate rectangles in the new strip (y 64..74) --")
CAND = [
    ("J8 pad row   x  0..50  y 66.4..68.4", (0.0, 66.4, 50.0, 68.4)),
    ("J10 pad row  x  0..50  y 69.6..71.6", (0.0, 69.6, 50.0, 71.6)),
    ("chip row     x 51..94  y 64.2..72.2", (51.0, 64.2, 94.0, 72.2)),
    ("chip row up  x 51..94  y 64.0..72.0", (51.0, 64.0, 94.0, 72.0)),
    ("cap row      x 54..90  y 72.4..73.6", (54.0, 72.4, 90.0, 73.6)),
    ("R row        x  1..50  y 71.6..74.0", (1.0, 71.6, 50.0, 74.0)),
    ("whole left   x  0..50  y 64.0..74.0", (0.0, 64.0, 50.0, 74.0)),
    ("whole right  x 51..100 y 64.0..74.0", (51.0, 64.0, 100.0, 74.0)),
]
for label, rect in CAND:
    h = hits(rect)
    print("  %-36s %s" % (label, "FREE" if not h else "hit: " + ", ".join(h)))

print()
print("-- candidate rectangles above the voice chip (for R6-R9 near J6) --")
CAND2 = [
    ("y 14..26   x 43..71", (43.0, 14.0, 71.0, 26.0)),
    ("y 17..26   x 43..71", (43.0, 17.0, 71.0, 26.0)),
    ("y 20..26   x 43..71", (43.0, 20.0, 71.0, 26.0)),
    ("y 22..26   x 43..71", (43.0, 22.0, 71.0, 26.0)),
]
for label, rect in CAND2:
    h = hits(rect)
    print("  %-22s %s" % (label, "FREE" if not h else "hit: " + ", ".join(h)))

e = board.GetBoardEdgesBoundingBox()
print()
print("outline x %.2f..%.2f  y %.2f..%.2f"
      % (e.GetLeft() / S, e.GetRight() / S, e.GetTop() / S, e.GetBottom() / S))
print("tracks %d   vias %d   zones %d   footprints %d"
      % (len(list(board.GetTracks())),
         sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA"),
         len(list(board.Zones())), len(list(board.GetFootprints()))))
