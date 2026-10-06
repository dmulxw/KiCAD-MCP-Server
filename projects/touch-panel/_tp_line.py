"""Cell-by-cell picture of the crossing, for one net and one y.

_tp_wall.py says a ROW16 route must cross 4 blocked F.Cu cells -- i.e. A* would
have to punch through the GND spine, which it refuses to do.  But that is only
the cheapest *cell* cost; a via pair that ducks under the spine on B.Cu would
cost 0 blocked cells if B.Cu is open there.  A* pays VIA_COST but is never
forbidden a via, so if that detour existed A* would have taken it and the wall
cost would have come back 0.  It did not, so something else closes the detour:
either B.Cu is blocked under the spine, or via_ok() vetoes the landing sites.
This prints the bit that decides it.

  python _tp_line.py ROW16 210.2
"""
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

NET = sys.argv[1] if len(sys.argv) > 1 else "ROW16"
YC = float(sys.argv[2]) if len(sys.argv) > 2 else 210.2

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

w = R.WIDTHS.get(NET, R.DEFAULT_W)
blocked, via_blocked = rt.blocked_for(NET, w / 2.0)

# the net's own copper, as route_net builds it
conn = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
for (onet, layer, x1, y1, x2, y2, ww) in rt.frozen:
    if onet == NET:
        R.raster_seg(conn, layer, x1, y1, x2, y2, ww / 2.0)
for (vnet, vx, vy) in rt.frozen_vias:
    if vnet == NET:
        for layer in (0, 1):
            R.raster_circle(conn, layer, vx, vy, R.VIA_D / 2.0)

print("%s  y=%.2f  (grid row j=%d, cell centre %.2f)"
      % (NET, YC, R.gj(YC), R.my(R.gj(YC))))
print("legend: F/B = blocked on that layer; 'o' = this net's own copper;"
      " 'v' = via_ok false")
print()

for dy in (-1.2, -0.6, 0.0, 0.6, 1.2):
    y = YC + dy
    j = R.gj(y)
    s = ""
    for i in range(R.gi(96.0), R.gi(104.0) + 1):
        if blocked[0, i, j]:
            s += "F"
        elif conn[0, i, j]:
            s += "o"
        else:
            s += "."
        if blocked[1, i, j]:
            s += "B"
        elif conn[1, i, j]:
            s += "o"
        else:
            s += "."
        if not rt.via_ok(R.mx(i), R.my(j)):
            s = s[:-1] + "v"
        s += " "
    print("y=%7.2f %s" % (y, s))

print()
hdr = "          "
for i in range(R.gi(96.0), R.gi(104.0) + 1):
    hdr += ("%-5.1f" % R.mx(i))
print(hdr)
print("          " + "".join("F B  " for _ in range(R.gi(96.0), R.gi(104.0) + 1)))
