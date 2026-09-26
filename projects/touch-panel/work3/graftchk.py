"""How badly does another board's ROW3/ROW5 copper clash with this one?

Grafting a routed net from an older revision is only viable if its path still
threads through the *current* board's copper. Build the distance map from
every other-net item on the target, then walk each candidate track's centreline
and read the gap off it.
"""
import sys
from collections import defaultdict

import numpy as np
import pcbnew

from probe import NGrid, item_shape

S = 1e6
STEP = float(__import__("os").environ.get("GSTEP", "0.1"))


def main():
    target, source, nets = sys.argv[1], sys.argv[2], sys.argv[3:]
    tb = pcbnew.LoadBoard(target)
    sb = pcbnew.LoadBoard(source)

    # obstacles = the target board's copper, excluding the nets we are grafting
    others = [t for t in tb.GetTracks() if t.GetNetname() not in nets]
    for fp in tb.GetFootprints():
        others += [p for p in fp.Pads() if p.GetNetname() not in nets]
    print(f"target obstacles: {len(others)} other-net item(s), grafting {nets}")

    for name in nets:
        cand = [t for t in sb.GetTracks() if t.GetNetname() == name]
        if not cand:
            print(f"\n{name}: nothing in source")
            continue
        widths = [t.GetWidth() / S for t in cand]
        w = max(widths)
        keep = 0.2 + w / 2

        grid = NGrid(tb, STEP, keep, 0.5 + w / 2, keep, keep,
                     [pcbnew.F_Cu, pcbnew.B_Cu])
        grid.build(others)

        bad = defaultdict(lambda: [0, 1e9, ""])
        npos = 0
        for t in cand:
            s, e = t.GetStart(), t.GetEnd()
            x0, y0 = s.x / S, s.y / S
            x1, y1 = e.x / S, e.y / S
            L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            n = max(2, int(L / STEP) + 1)
            lay = t.GetLayer()
            for k in range(n + 1):
                u = k / n
                x, y = x0 + u * (x1 - x0), y0 + u * (y1 - y0)
                i, j = grid.ij(x, y)
                if not (0 <= i < grid.nx and 0 <= j < grid.ny):
                    continue
                npos += 1
                d = float(grid.D[lay][j, i])
                if d < keep:
                    o = int(grid.OWN[lay][j, i])
                    if o < 0:
                        continue
                    it = others[o]
                    net = it.GetNetname()
                    kind = ("pad" if isinstance(it, pcbnew.PAD)
                            else "via" if isinstance(it, pcbnew.PCB_VIA) else "trk")
                    bad[net][0] += 1
                    bad[net][1] = min(bad[net][1], d)
                    bad[net][2] = kind
        print(f"\n=== {name} ({len(cand)} item(s), w{w:.3f}, keep {keep:.3f}) ===")
        print(f"  sampled {npos} point(s); {len(bad)} net(s) violated")
        for net, (c, worst, kind) in sorted(bad.items(), key=lambda kv: -kv[1][0]):
            print(f"     {net:<10} {c:5d} pt(s)  worst {worst:+.3f}mm  ({kind})")


if __name__ == "__main__":
    main()
