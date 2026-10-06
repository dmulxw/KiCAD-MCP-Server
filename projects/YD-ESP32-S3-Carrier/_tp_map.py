"""Where is each panel net, over the whole board rather than one margin?

_tp_where.py showed six CSEL nets with no copper in either margin at all, which
is either "they live in the middle" or "they are 3 mm stubs hanging off a header
pin".  Those are very different answers for a 595 that has to reach them, so get
the whole picture: per net, the bounding box, the total length, and a coarse
10 mm y-histogram of where the copper sits.
"""
import collections

import pcbnew

b = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")
S = 1e6

NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]

box = collections.defaultdict(lambda: [1e9, 1e9, -1e9, -1e9, 0.0, 0])
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    if not n:
        continue
    r = box[n]
    for p in (s, e):
        r[0] = min(r[0], p.x / S); r[1] = min(r[1], p.y / S)
        r[2] = max(r[2], p.x / S); r[3] = max(r[3], p.y / S)
    r[4] += pcbnew.ToMM(t.GetLength())
    r[5] += 1
for fp in b.GetFootprints():
    ref = fp.GetReference()
    for p in fp.Pads():
        n = p.GetNetname()
        if not n:
            continue
        r = box[n]
        q = p.GetPosition()
        r[0] = min(r[0], q.x / S); r[1] = min(r[1], q.y / S)
        r[2] = max(r[2], q.x / S); r[3] = max(r[3], q.y / S)
        r[5] += 1

print("net      bbox x            bbox y             len     items")
for n in NAMES + ["GND", "+3V3"]:
    if n not in box:
        print("  %-6s  ABSENT" % n)
        continue
    x0, y0, x1, y1, L, n_it = box[n]
    print("  %-6s x %6.1f..%6.1f   y %6.1f..%6.1f   %6.0f  %4d"
          % (n, x0, x1, y0, y1, L, n_it))

# Coarse y-histogram: which 10 mm bands does each net's copper occupy?
print("\n10 mm y-bands containing >1 mm of each net's copper")
BANDS = [(100 + 10 * k, 110 + 10 * k) for k in range(15)]
band_pts = collections.defaultdict(lambda: collections.defaultdict(float))
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    if not n:
        continue
    my = (s.y + e.y) / 2.0 / S
    kk = int((my - 100) / 10)
    band_pts[n][kk] += pcbnew.ToMM(t.GetLength())
for fp in b.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if not n:
            continue
        my = p.GetPosition().y / S
        band_pts[n][int((my - 100) / 10)] += 0.5
hdr = "  %-6s " % "net" + "".join("%5d-%3d" % (a, a + 10) for a, _ in BANDS)
print(hdr)
for n in NAMES + ["GND", "+3V3"]:
    d = band_pts.get(n, {})
    cells = "".join(("%5.0f" % d[k]) if d.get(k, 0.0) >= 1.0 else "    ."
                    for k, _ in enumerate(BANDS))
    print("  %-6s %s" % (n, cells))
