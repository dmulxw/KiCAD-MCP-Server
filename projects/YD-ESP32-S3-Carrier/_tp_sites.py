"""Where can a 595 actually stand on the board as it is?

_tp_places_orig.json holds the legal SOIC-16 centres _tp_place.py found on
touch-panel.kicad_pcb as it stands.  "488 sites" sounds like plenty until you
remember that a legal centre already implies its whole 7.4 x 10.4mm courtyard is
clear -- so two centres 0.25mm apart are the same placement, not two.  Cluster
them into blobs and print the blobs: that is the real standing room, and it is
what decides whether four chips fit beside J1A and J1B.
"""
import collections
import json
import sys

import numpy as np

STEP = 0.25
ALL = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "_tp_places_orig.json"))
SITES = [tuple(s) for s in ALL["all_sites"]]
print("sites: %d" % len(SITES))

cell = {}
for side, x, y in SITES:
    cell[(int(round(x / STEP)), int(round(y / STEP)))] = (side, x, y)
print("distinct grid cells: %d" % len(cell))

# 4-connected blobs = placements that touch (so one courtyard chain)
seen = set()
blobs = []
for k in cell:
    if k in seen:
        continue
    q = [k]
    seen.add(k)
    got = []
    while q:
        c = q.pop()
        got.append(c)
        i, j = c
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (i + d[0], j + d[1])
            if n in cell and n not in seen:
                seen.add(n)
                q.append(n)
    blobs.append(got)

blobs.sort(key=len, reverse=True)
print("\n%d blobs\n" % len(blobs))
print("  %6s  %-16s %-24s %-24s  %s"
      % ("sites", "sides", "centre-x span", "centre-y span", "implied clear box"))
for b in blobs:
    xs = [cell[c][1] for c in b]
    ys = [cell[c][2] for c in b]
    sd = collections.Counter(cell[c][0] for c in b)
    # a centre at x with a legal courtyard means x-3.7 .. x+3.7 is clear, so the
    # clear box spanned by the blob is the centre span grown by the courtyard.
    print("  %6d  %-16s %8.2f..%8.2f   %8.2f..%8.2f   %5.1f x %5.1f mm  (%.1f, %.1f) long=%.1f"
          % (len(b), ",".join("%s%d" % (k, v) for k, v in sd.most_common()),
             min(xs), max(xs), min(ys), max(ys),
             max(xs) - min(xs) + 7.4, max(ys) - min(ys) + 10.4,
             (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
             max(ys) - min(ys)))
