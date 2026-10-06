"""The weave in full, and where it leaves the column.

The falsification test is now settled on both axes.  Positive: the lift fixes 13
nets.  Negative: on its own it takes unconnected 59 -> 68, because it strands the
21 pad-2 GND terminals the weave was feeding.  So the removal is necessary but
not sufficient, and the replacement is mandatory.

This dumps what the replacement has to reproduce:

  1. every F.Cu GND segment wholly inside the box, with real endpoints;
  2. every F.Cu GND segment that only *reaches* the box -- those are the weave's
     anchors to the rest of the GND net, and each is a place the B.Cu copy has to
     come back up;
  3. the endpoints of (1) that land on (2) or on a GND pad.

  python _tp_weave.py
"""
from collections import Counter, defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X0, X1 = 100.40, 102.45
Y0, Y1 = 105.0, 246.0
TOL = 0.005

board = pcbnew.LoadBoard(BOARD)
TAPS = 1.5          # a segment ending at 102.610 is a pad-2 tap


def ends(t):
    s, e = t.GetStart(), t.GetEnd()
    return (TO(s.x), TO(s.y)), (TO(e.x), TO(e.y))


inside, anchored, taps = [], [], []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.F_Cu:
        continue
    if t.GetNetname() != "GND":
        continue
    (x1, y1), (x2, y2) = ends(t)
    # a pad-2 tap: one end on x=102.610, the other west of it
    if abs(max(x1, x2) - 102.610) < TOL and min(x1, x2) < 102.45:
        taps.append(((x1, y1), (x2, y2), TO(t.GetWidth())))
    inbox = (min(x1, x2) >= X0 - TOL and max(x1, x2) <= X1 + TOL
             and min(y1, y2) >= Y0 - TOL and max(y1, y2) <= Y1 + TOL)
    if inbox:
        inside.append(((x1, y1), (x2, y2), TO(t.GetWidth())))
    elif (min(x1, x2) <= X1 + TOL and max(x1, x2) >= X0 - TOL
          and min(y1, y2) <= Y1 + TOL and max(y1, y2) >= Y0 - TOL):
        anchored.append(((x1, y1), (x2, y2), TO(t.GetWidth())))

print("=== %d segment(s) wholly inside the box (the weave) ===" % len(inside))
inside.sort(key=lambda s: min(s[0][1], s[1][1]))
for ((x1, y1), (x2, y2), w) in inside:
    print("   (%8.3f,%8.3f) -> (%8.3f,%8.3f)  w=%.2f" % (x1, y1, x2, y2, w))

print("\n=== %d segment(s) reaching in from outside (the weave's anchors) ==="
      % len(anchored))
anchored.sort(key=lambda s: min(s[0][1], s[1][1]))
for ((x1, y1), (x2, y2), w) in anchored:
    print("   (%8.3f,%8.3f) -> (%8.3f,%8.3f)  w=%.2f" % (x1, y1, x2, y2, w))

print("\n=== %d pad-2 tap(s) ===" % len(taps))
for ((x1, y1), (x2, y2), w) in sorted(taps, key=lambda s: s[0][1]):
    print("   (%8.3f,%8.3f) -> (%8.3f,%8.3f)  w=%.2f" % (x1, y1, x2, y2, w))

# ---- where the weave touches anything that is NOT the weave ----------------
print("\n=== weave endpoints landing on an anchor / another net ===")
foreign = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.F_Cu:
        continue
    if t.GetNetname() == "GND":
        continue
    (x1, y1), (x2, y2) = ends(t)
    foreign.append((t.GetNetname(), x1, y1, x2, y2, TO(t.GetWidth())))

pts = defaultdict(int)
for ((a), (b), w) in inside:
    pts[(round(a[0], 3), round(a[1], 3))] += 1
    pts[(round(b[0], 3), round(b[1], 3))] += 1

hitA = 0
for p, n in sorted(pts.items()):
    for ((a), (b), w) in anchored:
        for q in (a, b):
            if abs(q[0] - p[0]) < TOL and abs(q[1] - p[1]) < TOL:
                print("   %s  degree=%d  meets anchor %s" % (p, n, q))
                hitA += 1
print("   %d weave endpoint(s) land on an anchor" % hitA)

# ---- B.Cu occupancy as an x histogram, to find a lane for the trunk ---------
print("\n=== B.Cu: for each 0.2 mm x-column, how much of the height is used ===")
used = defaultdict(float)
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        x, y = TO(p.x), TO(p.y)
        w = TO(t.GetWidth(pcbnew.F_Cu))
        if not (X0 - 1 <= x <= X1 + 3 and Y0 <= y <= Y1):
            continue
        for k in range(int((x - w / 2 - 0.2) * 10), int((x + w / 2 + 0.2) * 10) + 1):
            used[k / 10.0] += 1.0
        continue
    if t.GetLayer() != pcbnew.B_Cu:
        continue
    (x1, y1), (x2, y2) = ends(t)
    w = TO(t.GetWidth())
    if max(y1, y2) < Y0 or min(y1, y2) > Y1:
        continue
    lo = min(x1, x2) - w / 2 - 0.2
    hi = max(x1, x2) + w / 2 + 0.2
    for k in range(int(lo * 10), int(hi * 10) + 1):
        used[k / 10.0] += abs(y2 - y1) + 0.2
for k in sorted(used):
    if 99.0 <= k <= 105.0:
        print("   x=%6.1f  %7.1f mm of the column blocked" % (k, used[k]))
