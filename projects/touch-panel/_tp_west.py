"""Where does each existing net stop on the west, and is the 595 near it?

The routing failure is a placement fact, not a search fact: the 595 column sits
west of a wall that is solid on both layers.  What the router actually needs is
the westmost point of each net's existing copper -- that is where a 595 output
has to land -- so this prints it per net, alongside the y of that point.
"""
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

WANT = (["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
        + ["DRV_CASC1", "DRV_CASC2", "DRV_CASC3", "IO9", "IO10", "IO11",
           "IO12", "+3V3", "GND"])

print("%-10s %6s %6s  %-26s %s" % ("net", "segs", "west", "at the westmost point", "pads"))
for net in WANT:
    pts = []
    for (onet, layer, x1, y1, x2, y2, w) in rt.frozen:
        if onet == net:
            pts.append((x1, y1, layer))
            pts.append((x2, y2, layer))
    if not pts:
        print("%-10s %6d %6s  %-26s %s" % (net, 0, "-", "no pre-existing copper",
                                           len(rt.pads.get(net, []))))
        continue
    pts.sort()
    x, y, l = pts[0]
    # every distinct column the net occupies, to spot a vertical run
    cols = sorted({round(p[0], 2) for p in pts})
    print("%-10s %6d %6.2f  (%.2f,%.2f) L%d   cols %s%s"
          % (net, len(pts) // 2, x, x, y, l, cols[:6],
             " ..." if len(cols) > 6 else ""))

print("\n--- 595 output pads, and how far east their net's copper starts ---")
for ref in ("U1", "U2", "U3", "U4"):
    fp = board.FindFootprintByReference(ref)
    for p in sorted(fp.Pads(), key=lambda q: int(q.GetNumber())):
        net = p.GetNetname()
        if not net or net in ("+3V3", "GND"):
            continue
        pos = p.GetPosition()
        px, py = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        west = None
        for (onet, layer, x1, y1, x2, y2, w) in rt.frozen:
            if onet == net:
                for (xx, yy) in ((x1, y1), (x2, y2)):
                    d = ((xx - px) ** 2 + (yy - py) ** 2) ** 0.5
                    if west is None or d < west[0]:
                        west = (d, xx, yy, layer)
        if west is None:
            print("  %s.%-3s %-9s (%7.2f,%7.2f)  no existing copper"
                  % (ref, p.GetNumber(), net, px, py))
        else:
            print("  %s.%-3s %-9s (%7.2f,%7.2f)  nearest existing copper "
                  "%.2f mm away at (%.2f,%.2f) L%d"
                  % (ref, p.GetNumber(), net, px, py, west[0], west[1], west[2],
                     west[3]))
