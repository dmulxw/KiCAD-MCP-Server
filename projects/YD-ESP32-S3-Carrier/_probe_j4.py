"""What seals the GND pocket around J4.7?

_fix_islands.py can now try a track as well as a via, and says why it gave up:
every short run from the pocket to the plane on B.Cu is blocked by an IO14, +5V
or IO18 trace, and on F.Cu by IO18.  A wall, not a gap.  So print the wall --
every pad and every track in the neighbourhood, with endpoints, so the move that
opens a throat can be a measured one.

  python _probe_j4.py [board.kicad_pcb]
"""
import sys

import pcbnew

BASE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
BOARD = sys.argv[1] if len(sys.argv) > 1 else BASE + r"\_v90_fix2.kicad_pcb"

X0, Y0, X1, Y1 = 77.0, 40.0, 87.0, 50.0

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)
TO = pcbnew.ToMM
FROM = pcbnew.FromMM

print("=== pads in the box ===")
for fp in board.GetFootprints():
    for p in fp.Pads():
        pos = p.GetPosition()
        x, y = TO(pos.x), TO(pos.y)
        if not (X0 <= x <= X1 and Y0 <= y <= Y1):
            continue
        lay = ",".join(board.GetLayerName(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)
                       if p.IsOnLayer(l))
        print("  %-7s (%7.3f,%7.3f)  %-8s %.2fx%.2f  %-9s drill %.2f"
              % (str(fp.GetReference()) + "." + str(p.GetNumber()), x, y,
                 str(p.GetNetname()), TO(p.GetSize().x), TO(p.GetSize().y),
                 lay, TO(p.GetDrillSize().x)))

print("\n=== tracks in the box (a track is in if either end is) ===")
rows = []
for t in board.GetTracks():
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    inside = any(X0 <= qx <= X1 and Y0 <= qy <= Y1 for qx, qy in
                 ((ax, ay), (bx, by), ((ax + bx) / 2, (ay + by) / 2)))
    if not inside:
        continue
    rows.append((str(t.GetNetname()), board.GetLayerName(t.GetLayer()),
                 ax, ay, bx, by, TO(t.GetWidth()),
                 "VIA" if t.GetClass() == "PCB_VIA" else ""))
for r in sorted(rows):
    print("  %-9s %-5s (%7.3f,%7.3f)-(%7.3f,%7.3f)  w %.2f %s"
          % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]))

print("\n=== clearance profile: distance from each track to the pocket ===")
# The pocket, from _probe_island_gap.py
PX, PY = 82.000, 46.240
best = {}
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA":
        continue
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        continue
    u = max(0.0, min(1.0, ((PX - ax) * dx + (PY - ay) * dy) / L2))
    d = ((PX - ax - u * dx) ** 2 + (PY - ay - u * dy) ** 2) ** 0.5 - TO(t.GetWidth()) / 2
    if d > 4.0:
        continue
    key = (str(t.GetNetname()), board.GetLayerName(t.GetLayer()))
    if key not in best or d < best[key][0]:
        best[key] = (d, ax + u * dx, ay + u * dy)
for k in sorted(best, key=lambda k: best[k][0]):
    d, cx, cy = best[k]
    print("  %-9s %-5s  %.3f mm from J4.7, nearest point (%6.2f,%6.2f)"
          % (k[0], k[1], d, cx, cy))
