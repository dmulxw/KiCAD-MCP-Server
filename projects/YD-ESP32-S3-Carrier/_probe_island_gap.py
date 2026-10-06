"""How far is each stranded GND pocket from the plane it should be part of?

_fix_islands.py places a via when a cell of the island sits directly over copper
that is already home.  Two islands have no such cell, and the reason turns out to
be the same for both: they are the only GND copper in their neighbourhood, so
there is nothing opposite to weld to.  That makes the question a distance one --
how far, and across what -- which decides the fix:

  a fraction of a millimetre of bare board -> a short GND track closes it
  the far side of someone else's traces -> the pocket needs a routing change

Both pockets are anchored by a real through-hole GND pad (J4.7, SW1.2), which is
why the filler's island removal keeps them; that pad is the natural place for a
track to start, so this also reports the nearest *home* GND pad, since routing
pad-to-pad needs no new primitive.

  python _probe_island_gap.py [board.kicad_pcb]
"""
import sys
from collections import deque

import pcbnew

BASE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
sys.path.insert(0, BASE)
import _fix_islands as F  # noqa: E402  (guarded, so importing pours nothing)

BOARD = sys.argv[1] if len(sys.argv) > 1 else BASE + r"\_v90.kicad_pcb"

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)
TO = pcbnew.ToMM

buf = F.raster(board)
comp = {}
for l in F.LAY:
    ids, n, boxes = F.label(buf[l])
    buf[l] = ids
    for c in range(n):
        comp[(l, c)] = sum(1 for v in ids if v == c)
        comp[(l, c, "bbox")] = boxes[c]
    print("%-5s %4d component(s)" % ("F.Cu" if l == pcbnew.F_Cu else "B.Cu", n))
    big = sorted((comp[(l, c)] for c in range(n)), reverse=True)[:4]
    print("      largest: " + ", ".join("%.1f mm2" % (b * F.GRID * F.GRID)
                                        for b in big))

HOME_MIN = 3000          # cells; 3000 * 0.04 mm2 = 120 mm2 -- plainly the plane

TARGETS = [("J4.7", 82.000, 46.240), ("SW1.2", 49.000, 59.000)]

# Multi-source BFS from every home cell.  8-connected on the grid, so a step is
# at most 0.28 mm; for a gap of a few tenths that is the same answer as a true
# Euclidean distance and it needs no priority queue.
for name, px, py in TARGETS:
    print("\n=== %s at (%.3f,%.3f) ===" % (name, px, py))
    px = px
    for l, tag in ((pcbnew.F_Cu, "F.Cu"), (pcbnew.B_Cu, "B.Cu")):
        ids = buf[l]
        N = F.NX * F.NY
        dist = [-1] * N
        src = [-1] * N
        q = deque()
        for k in range(N):
            c = ids[k]
            if c >= 0 and comp[(l, c)] >= HOME_MIN:
                dist[k] = 0
                src[k] = k
                q.append(k)
        if not q:
            print("  %-5s no plane-sized component on this layer" % tag)
            continue
        while q:
            k = q.popleft()
            i, j = k % F.NX, k // F.NX
            for di in (-1, 0, 1):
                ii = i + di
                if not (0 <= ii < F.NX):
                    continue
                for dj in (-1, 0, 1):
                    jj = j + dj
                    if not (0 <= jj < F.NY):
                        continue
                    kk = jj * F.NX + ii
                    if dist[kk] < 0:
                        dist[kk] = dist[k] + 1
                        src[kk] = src[k]
                        q.append(kk)

        # the island's own component: whatever covers the pad centre
        i0, j0 = int(round(px / F.GRID)), int(round(py / F.GRID))
        mine = -1
        for r in range(0, 4):
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    ii, jj = i0 + di, j0 + dj
                    if 0 <= ii < F.NX and 0 <= jj < F.NY:
                        v = ids[jj * F.NX + ii]
                        if v >= 0:
                            mine = v
                            break
                if mine >= 0:
                    break
            if mine >= 0:
                break
        if mine < 0:
            print("  %-5s no pour at the pad centre" % tag)
            continue
        x0, x1, y0, y1 = comp[(l, mine, "bbox")]
        best = None
        for i in range(int(x0 / F.GRID), int(x1 / F.GRID) + 1):
            for j in range(int(y0 / F.GRID), int(y1 / F.GRID) + 1):
                k = j * F.NX + i
                if ids[k] != mine or dist[k] < 0:
                    continue
                if best is None or dist[k] < best[0]:
                    best = (dist[k], i, j, src[k])
        if best is None:
            print("  %-5s island %.1f mm2 is UNREACHABLE from the plane "
                  "(walled in)" % (tag, comp[(l, mine)] * F.GRID * F.GRID))
            continue
        d, i, j, k2 = best
        print("  %-5s island %5.1f mm2  ->  plane %.2f mm away, "
              "island cell (%5.2f,%5.2f) -> plane cell (%5.2f,%5.2f)"
              % (tag, comp[(l, mine)] * F.GRID * F.GRID, d * F.GRID,
                 i * F.GRID, j * F.GRID,
                 (k2 % F.NX) * F.GRID, (k2 // F.NX) * F.GRID))
        # The BFS steps through anything, so it measures free space, not a
        # corridor.  A track can only take the gap if nothing else is in it --
        # walk the straight line and name every piece of foreign copper it
        # crosses, plus whether pour is under the line at all.
        print("      corridor:")
        hit = {}
        pour_under = 0
        steps = int(d * F.GRID / 0.05) + 1
        for s in range(steps + 1):
            t = s / float(steps)
            cx = (i + ((k2 % F.NX) - i) * t) * F.GRID
            cy = (j + ((k2 // F.NX) - j) * t) * F.GRID
            pos = pcbnew.VECTOR2I(pcbnew.FromMM(cx), pcbnew.FromMM(cy))
            if ids[int(round(cy / F.GRID)) * F.NX + int(round(cx / F.GRID))] >= 0:
                pour_under += 1
            for t2 in board.GetTracks():
                if not t2.IsOnLayer(l):
                    continue
                if t2.HitTest(pos):
                    nm = str(t2.GetNetname()) or "-"
                    if nm != "GND":
                        hit[nm] = hit.get(nm, 0) + 1
        for k in sorted(hit, key=lambda k: -hit[k]):
            print("        %-10s crossed %d sample(s)" % (k, hit[k]))
        print("        %d sample(s) over GND pour, %d over bare board"
              % (pour_under, steps + 1 - pour_under))
        if not hit:
            print("        NO foreign copper on the line -- a GND track fits")

    # Which GND pads are already home?  A track there needs no new primitive.
    print("  GND pads within 8 mm, and how far:")
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if str(p.GetNetname()) != "GND":
                continue
            pos = p.GetPosition()
            qx, qy = TO(pos.x), TO(pos.y)
            d = ((qx - px) ** 2 + (qy - py) ** 2) ** 0.5
            if d > 8.0:
                continue
            lay = ",".join(board.GetLayerName(x) for x in (pcbnew.F_Cu, pcbnew.B_Cu)
                           if p.IsOnLayer(x))
            print("    %-8s (%7.3f,%7.3f)  %5.2f mm  %.2fx%.2f  %s"
                  % (str(fp.GetReference()) + "." + str(p.GetNumber()),
                     qx, qy, d, TO(p.GetSize().x), TO(p.GetSize().y), lay))
