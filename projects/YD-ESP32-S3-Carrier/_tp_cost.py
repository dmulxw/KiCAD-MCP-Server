"""How far is each panel net's copper from each candidate 595 site?

The map (_tp_map.py) says where every net is; this asks the placement question
directly.  For a chip at site S, an output pad has to reach the net's copper, so
the natural cost of putting net n on a chip at S is the distance from S to the
nearest millimeter of n -- and because the six CSEL0/1/2/7/8/9 nets exist ONLY in
the bottom strip, that one number already separates the feasible sites from the
hopeless ones.

Cost is Euclidean and ignores obstacles, so it is a candidate ranking, not a
verdict; the A* run that follows is the verdict.  What it is good at is choosing
WHERE to put the four chips before spending an hour of search on the question.
"""
import collections

import numpy as np
import pcbnew

b = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")
S = 1e6
NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]

pts = collections.defaultdict(list)
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    if not n:
        continue
    x0, y0 = s.x / S, s.y / S
    x1, y1 = e.x / S, e.y / S
    steps = max(2, int((((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5) / 0.5) + 1)
    for k in range(steps + 1):
        f = k / steps
        pts[n].append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
for fp in b.GetFootprints():
    for p in fp.Pads():
        q = p.GetPosition()
        pts[p.GetNetname()].append((q.x / S, q.y / S))

P = {n: np.array(pts[n]) for n in NAMES if pts.get(n)}

print("candidate 595 sites (footprint centre; SOIC-16 courtyard 7.49 x 10.49)")
SITES = [("L108", 95.0, 108.0), ("L170", 95.0, 170.0), ("L178", 95.0, 178.0),
         ("L188", 95.0, 188.0), ("L198", 95.0, 198.0), ("L208", 95.0, 208.0),
         ("L218", 95.0, 218.0), ("L228", 95.0, 228.0), ("L238", 95.0, 238.0),
         ("R108", 174.0, 108.0), ("R118", 174.0, 118.0), ("R128", 174.0, 128.0),
         ("R138", 174.0, 138.0), ("R148", 174.0, 148.0), ("R158", 174.0, 158.0),
         ("R168", 174.0, 168.0), ("R240", 174.0, 240.0)]

D = np.zeros((len(NAMES), len(SITES)))
for r, n in enumerate(NAMES):
    if n not in P:
        D[r, :] = 999.0
        continue
    a = P[n]
    for c, (_, x, y) in enumerate(SITES):
        D[r, c] = np.min(np.hypot(a[:, 0] - x, a[:, 1] - y))

w = 6
print("%-6s %s" % ("net", "".join("%*s" % (w, s[0]) for s in SITES)))
for r, n in enumerate(NAMES):
    print("  %-6s %s" % (n, "".join("%*s" % (w, "%.0f" % D[r, c])
                                    if D[r, c] < 999 else "%*s" % (w, "-")
                                    for c in range(len(SITES)))))

# Best pair of sites per side, and the split that puts 8 nets on each chip.
LEFT = [c for c, s in enumerate(SITES) if s[0][0] == "L"]
RIGHT = [c for c, s in enumerate(SITES) if s[0][0] == "R"]


def best_two(cols):
    """For each pair of columns in `cols`, the cost of assigning every net to
    its cheaper of the two -- a lower bound on a split that must also respect
    the 8-per-chip capacity."""
    out = []
    for a in range(len(cols)):
        for bct in range(a + 1, len(cols)):
            c1, c2 = cols[a], cols[bct]
            m = np.minimum(D[:, c1], D[:, c2])
            out.append((float(m.sum()), float(m.max()), c1, c2))
    return sorted(out)


print("\nbest left  pairs (sum then worst net):")
for t in best_two(LEFT)[:6]:
    print("   %-22s-%22s sum %6.0f  worst %5.1f"
          % (SITES[t[2]][0], SITES[t[3]][0], t[0], t[1]))
print("best right pairs (sum then worst net):")
for t in best_two(RIGHT)[:6]:
    print("   %-22s-%22s sum %6.0f  worst %5.1f"
          % (SITES[t[2]][0], SITES[t[3]][0], t[0], t[1]))
