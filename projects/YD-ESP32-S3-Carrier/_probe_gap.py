"""How far is each new pad from its net's own pre-existing copper?

HEAD routed every ROW/CSEL net from the ESP32 module to the panel header.  The
595 strip re-sources them from U3-U6 at the bottom of the board, so each new pad
only has to *join* copper that is already there -- absorb() puts that copper in
router.frozen and route_net targets it.  If the gap is a millimetre the failure
is congestion; if it is 80 mm the net was never fully routed at HEAD either and
the strip is asking for a connection that does not exist yet.

Also reports the nearest foreign copper, so a pad walled in by a neighbour is
distinguishable from one that is merely far from home.

    python _probe_gap.py ROW1 CSEL0 ROW18 +3V3
"""
import sys, os
from collections import Counter

import pcbnew

S = 1e6
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")


def seg_pt(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0.0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


board = pcbnew.LoadBoard(BOARD)

for net in sys.argv[1:]:
    pads = []
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() == net:
                c = p.GetPosition()
                pads.append((f.GetReference(), p.GetNumber(), c.x / S, c.y / S, p))

    print("\n===== %s  (%d pad(s))" % (net, len(pads)), flush=True)
    if len(pads) < 2:
        print("   fewer than two pads -- nothing to route", flush=True)
        continue

    # every trace on this net, as (layer, a, b, w)
    own = [(t.GetLayerName(), (t.GetStart().x / S, t.GetStart().y / S),
            (t.GetEnd().x / S, t.GetEnd().y / S), t.GetWidth() / S)
           for t in board.GetTracks()
           if t.GetNetname() == net and t.Type() == pcbnew.PCB_TRACE_T]
    print("   %d trace(s) already on the net" % len(own), flush=True)

    for ref, num, px, py, pad in pads:
        if not own:
            print("   %-6s.%-3s (%.2f,%.2f)  NO EXISTING COPPER AT ALL"
                  % (ref, num, px, py), flush=True)
            continue
        # distance to the nearest same-net trace end, per the pad's own layers
        best = None
        for lay, a, b, w in own:
            d = seg_pt(a[0], a[1], b[0], b[1], px, py) - w / 2
            if best is None or d < best[0]:
                best = (d, lay, a, b)
        # nearest foreign trace, on the same layer, copper edge to pad centre
        near = Counter()
        for t in board.GetTracks():
            if t.GetNetname() == net or t.Type() != pcbnew.PCB_TRACE_T:
                continue
            a = (t.GetStart().x / S, t.GetStart().y / S)
            b = (t.GetEnd().x / S, t.GetEnd().y / S)
            d = seg_pt(a[0], a[1], b[0], b[1], px, py) - t.GetWidth() / S / 2
            if d < 1.0:
                near[(t.GetNetname() or "-", t.GetLayerName())] += 1
        d, lay, a, b = best
        print("   %-6s.%-3s (%.2f,%.2f)  own copper %.2f mm away [%s]   "
              "within 1.0mm: %s"
              % (ref, num, px, py, d, lay,
                 ", ".join("%s/%s" % k for k in near) or "nothing"), flush=True)
