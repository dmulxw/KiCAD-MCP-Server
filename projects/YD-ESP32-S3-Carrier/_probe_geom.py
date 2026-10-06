"""Measure the two boards that have to mate.

Two questions, both geometric, both answerable from the files:

  1. The panel's J1A/J1B -- where exactly, which way do they run, and what is
     the offset between them?  A direct plug-on mate requires the carrier's
     sockets to sit at the SAME relative offset, so this number decides whether
     a direct mate is even possible.

  2. The carrier's free area -- after the footprint bounding boxes are laid
     down, which rectangles are actually empty?  "There is room above the voice
     chip" is a claim that needs a rectangle, not an impression.
"""
import sys

import pcbnew

S = 1e6
TP = "../touch-panel/touch-panel.kicad_pcb"
YD = "YD-ESP32-S3-Carrier.kicad_pcb"


def bbox(fp):
    b = fp.GetBoundingBox()
    return (b.GetLeft() / S, b.GetTop() / S, b.GetRight() / S, b.GetBottom() / S)


print("=" * 72)
print("PANEL  %s" % TP)
b = pcbnew.LoadBoard(TP)
e = b.GetBoardEdgesBoundingBox()
print("outline x %.2f..%.2f  y %.2f..%.2f   (%.2f x %.2f mm)"
      % (e.GetLeft() / S, e.GetRight() / S, e.GetTop() / S, e.GetBottom() / S,
         (e.GetRight() - e.GetLeft()) / S, (e.GetBottom() - e.GetTop()) / S))
hdrs = {}
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref not in ("J1A", "J1B"):
        continue
    c = fp.GetPosition()
    bb = bbox(fp)
    # Pad span tells us which way the row runs without trusting the rotation.
    xs = [p.GetPosition().x / S for p in fp.Pads()]
    ys = [p.GetPosition().y / S for p in fp.Pads()]
    hdrs[ref] = (c.x / S, c.y / S)
    print("%s  origin (%.2f, %.2f)  rot %.0f  %d pad(s)"
          % (ref, c.x / S, c.y / S, fp.GetOrientationDegrees(), len(list(fp.Pads()))))
    print("    pad span x %.2f..%.2f (%.2f)   y %.2f..%.2f (%.2f)"
          % (min(xs), max(xs), max(xs) - min(xs), min(ys), max(ys), max(ys) - min(ys)))
    print("    body bbox x %.2f..%.2f  y %.2f..%.2f" % bb)

if len(hdrs) == 2:
    dx = hdrs["J1B"][0] - hdrs["J1A"][0]
    dy = hdrs["J1B"][1] - hdrs["J1A"][1]
    print("offset J1A->J1B:  dx %.2f  dy %.2f   |d| %.2f mm" % (dx, dy, (dx * dx + dy * dy) ** 0.5))
    span = 19 * 2.54
    print("each header is %.2f mm long along y" % span)
    print("=> a DIRECT plug-on needs the carrier to span y by %.2f mm"
          % (abs(dy) + span))
    print("=> and x by %.2f mm" % (abs(dx) + 2 * 1.3))

print()
print("=" * 72)
print("CARRIER  %s" % YD)
b = pcbnew.LoadBoard(YD)
e = b.GetBoardEdgesBoundingBox()
print("outline x %.2f..%.2f  y %.2f..%.2f   (%.2f x %.2f mm)"
      % (e.GetLeft() / S, e.GetRight() / S, e.GetTop() / S, e.GetBottom() / S,
         (e.GetRight() - e.GetLeft()) / S, (e.GetBottom() - e.GetTop()) / S))

print("\n-- footprints, sorted by x --")
rows = []
for fp in b.GetFootprints():
    bb = bbox(fp)
    rows.append((fp.GetReference(), bb, str(fp.GetFPID().GetLibItemName())))
for ref, bb, name in sorted(rows, key=lambda r: r[1][0]):
    print("  %-6s x %6.2f..%6.2f  y %6.2f..%6.2f   %s"
          % (ref, bb[0], bb[2], bb[1], bb[3], name))

# Three candidate strips, each a question the write-up has to answer with a
# yes or a no rather than an impression.
print("\n-- candidate free strips (no footprint bbox overlaps the rectangle) --")
X0, X1 = e.GetLeft() / S, e.GetRight() / S
Y0, Y1 = e.GetTop() / S, e.GetBottom() / S
strips = [
    ("A  top strip       y 14.0..26.0", 8.0, X1 - 8.0, 14.0, 26.0),
    ("B  bottom strip    y 62.0..63.9", 8.0, X1 - 8.0, 62.0, Y1 - 0.2),
    ("C  below board +10 y 64.0..74.0", 0.0, X1, Y1 - 0.2, Y1 + 10.0),
    ("D  left of module  x  2.0.. 7.0", 2.0, 7.0, 14.0, Y1 - 0.2),
]
for label, x0, x1, y0, y1 in strips:
    hits = [ref for ref, bb, _ in rows
            if not (bb[2] < x0 or bb[0] > x1 or bb[3] < y0 or bb[1] > y1)]
    print("  %-34s  %.0f x %.0f mm   %s"
          % (label, x1 - x0, y1 - y0,
             "FREE" if not hits else "occupied by %s" % ", ".join(sorted(hits))))
