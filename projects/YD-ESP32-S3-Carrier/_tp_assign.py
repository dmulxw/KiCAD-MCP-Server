"""Pick the best four sites and the 8-net split that goes with them.

_tp_cost.py ranked sites one at a time, which is the wrong question: a chip has
eight outputs, so what matters is the cost of the split that a PAIR of sites
induces under a capacity of eight.  Two sites can each look mediocre alone and
together cover sixteen nets cheaply.

So: all C(9,2) left pairs x C(8,2) right pairs, each solved by the obvious greedy
(cheapest net-site pair first, skip when either end is full) and scored on the
sum of the chosen distances plus the worst single net.  Greedy is not optimal but
it is exact enough to rank a thousand candidates, and the winner is then checked
by the A* run.
"""
import itertools

import numpy as np
import pcbnew

b = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")
S = 1e6
NAMES = ["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]

import collections
pts = collections.defaultdict(list)
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    n = t.GetNetname()
    if not n:
        continue
    x0, y0, x1, y1 = s.x / S, s.y / S, e.x / S, e.y / S
    steps = max(2, int((((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5) / 0.5) + 1)
    for k in range(steps + 1):
        f = k / steps
        pts[n].append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
for fp in b.GetFootprints():
    for p in fp.Pads():
        q = p.GetPosition()
        pts[p.GetNetname()].append((q.x / S, q.y / S))

SITES = [("L108", 95.0, 108.0), ("L170", 95.0, 170.0), ("L178", 95.0, 178.0),
         ("L188", 95.0, 188.0), ("L198", 95.0, 198.0), ("L208", 95.0, 208.0),
         ("L218", 95.0, 218.0), ("L228", 95.0, 228.0), ("L238", 95.0, 238.0),
         ("R108", 174.0, 108.0), ("R118", 174.0, 118.0), ("R128", 174.0, 128.0),
         ("R138", 174.0, 138.0), ("R148", 174.0, 148.0), ("R158", 174.0, 158.0),
         ("R168", 174.0, 168.0), ("R240", 174.0, 240.0)]

D = np.zeros((len(NAMES), len(SITES)))
for r, n in enumerate(NAMES):
    a = np.array(pts[n]) if pts.get(n) else np.zeros((1, 2))
    for c, (_, x, y) in enumerate(SITES):
        D[r, c] = np.min(np.hypot(a[:, 0] - x, a[:, 1] - y))

LEFT = [c for c, s in enumerate(SITES) if s[0][0] == "L"]
RIGHT = [c for c, s in enumerate(SITES) if s[0][0] == "R"]
CAP = 8


def greedy(cols):
    """Assign all 31 nets to the 4 sites, 8 per site, cheapest pair first."""
    pairs = sorted(((D[r, c], r, c) for r in range(len(NAMES)) for c in cols))
    used = {c: 0 for c in cols}
    got = {}
    for d, r, c in pairs:
        if r in got or used[c] >= CAP:
            continue
        got[r] = (c, d)
        used[c] += 1
    if len(got) < len(NAMES):
        return None
    return got


best = []
for lp in itertools.combinations(LEFT, 2):
    for rp in itertools.combinations(RIGHT, 2):
        got = greedy(list(lp) + list(rp))
        if got is None:
            continue
        tot = sum(d for _, d in got.values())
        worst = max(d for _, d in got.values())
        best.append((tot, worst, lp, rp, got))
best.sort(key=lambda t: (t[0] + 4.0 * t[1], t[1]))

for i, (tot, worst, lp, rp, got) in enumerate(best[:5]):
    print("#%d  sites %s + %s   sum %.0f  worst %.1f"
          % (i + 1, [SITES[c][0] for c in lp], [SITES[c][0] for c in rp], tot, worst))

tot, worst, lp, rp, got = best[0]
print("\nchosen: left %s   right %s" % ([SITES[c][0] for c in lp],
                                        [SITES[c][0] for c in rp]))
by = {}
for r, (c, d) in got.items():
    by.setdefault(c, []).append((NAMES[r], d))
for c in sorted(by, key=lambda c: SITES[c][0]):
    nets = sorted(by[c], key=lambda t: t[1])
    print("  %-6s (%.1f, %.1f)  %d nets, worst %4.1fmm: %s"
          % (SITES[c][0], SITES[c][1], SITES[c][2], len(nets),
             max(d for _, d in nets), " ".join("%s(%.0f)" % t for t in nets)))

import json
json.dump({SITES[c][0]: [n for n, _ in v] for c, v in by.items()},
          open("_tp_assign.json", "w"), indent=1)
print("\nwrote _tp_assign.json")
