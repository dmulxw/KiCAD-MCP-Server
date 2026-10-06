"""Is the router's via bigger than this board's?

VIA_D = 0.60 / VIA_DRILL = 0.30 came from the carrier's route.py.  The panel is
a different board: an FPC-facing sensor panel, not a 100x74 power board.  If its
own 529 vias are smaller, then `via_blocked` -- built at CLEAR + VIA_D/2 = 0.46,
a 0.15 mm shell wider than the trace's own 0.31 -- is reserving space for a via
this board would never use, and the CSELs are failing against a phantom.

Reports the size histogram of the vias actually on the board, the board's own
minimum via, and then re-runs the failing A* calls with VIA_D swept downward.
"""
import collections
import os
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                      # noqa: E402

NETS = [n for n in (sys.argv[1] if len(sys.argv) > 1
                    else "CSEL0,CSEL5,ROW20").split(",") if n]

board = pcbnew.LoadBoard(R.BOARD)

hist = collections.Counter()
drill = collections.Counter()
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        hist[round(pcbnew.ToMM(t.GetWidth()), 3)] += 1
        drill[round(pcbnew.ToMM(t.GetDrillValue()), 3)] += 1
print("vias on the board, by diameter:")
for d, n in sorted(hist.items()):
    print("   %.3f mm  x%d" % (d, n))
print("vias on the board, by drill:")
for d, n in sorted(drill.items()):
    print("   %.3f mm  x%d" % (d, n))

ds = board.GetDesignSettings()
print("\nboard design rules:")
for name, fn in (("m_ViasMinSize", lambda: ds.m_ViasMinSize),
                 ("m_MinThroughDrill", lambda: ds.m_MinThroughDrill),
                 ("m_TrackMinWidth", lambda: ds.m_TrackMinWidth),
                 ("m_MinClearance", lambda: ds.m_MinClearance)):
    try:
        print("   %-18s %.3f mm" % (name, pcbnew.ToMM(fn())))
    except Exception as exc:                              # noqa: BLE001
        print("   %-18s unavailable (%s)" % (name, exc))

# --- sweep VIA_D, rebuilding the masks each time ----------------------------
# blocked_for() reads the module-level VIA_D at call time, so patching it is
# enough; the rasterizers do not use it.
print("\nvia_blocked and A* by VIA_D (board untouched, real GND copper):")
orig_via_d = R.VIA_D
rt = R.Router(board)
R.absorb(board, rt)

for vd in (0.60, 0.50, 0.45, 0.40):
    R.VIA_D = vd
    R.VIA_DRILL = vd / 2.0
    line = []
    for NET in NETS:
        w = R.WIDTHS.get(NET, R.DEFAULT_W)
        blocked, via_blocked = rt.blocked_for(NET, w / 2.0)
        pads = rt.pads.get(NET, [])
        if len(pads) < 2:
            continue
        conn = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
        for (onet, layer, x1, y1, x2, y2, ww) in rt.frozen:
            if onet == NET:
                R.raster_seg(conn, layer, x1, y1, x2, y2, ww / 2.0)
        for (vnet, vx, vy) in rt.frozen_vias:
            if vnet == NET:
                for layer in (0, 1):
                    R.raster_circle(conn, layer, vx, vy, R.VIA_D / 2.0)
        _, _, n0, l0 = pads[0]
        for l in (l0 or (0, 1)):
            for (i, j) in n0:
                conn[l, i, j] = True
        seed = [(i, j, l) for l in (l0 or (0, 1)) for (i, j) in n0]
        reach = R.reachable(conn, seed, rt.via_ok)
        ok = 0
        for k in range(1, len(pads)):
            _, _, nodes, layers = pads[k]
            starts = [(i, j, l) for l in (layers or (0, 1))
                      for (i, j) in nodes]
            if rt.astar(blocked, via_blocked, starts, reach) is not None:
                ok += 1
        line.append("%s %d/%d vb=%d" % (NET, ok, len(pads) - 1,
                                        int(via_blocked.sum())))
    print("   VIA_D=%.2f  %s" % (vd, " | ".join(line)))

R.VIA_D = orig_via_d
