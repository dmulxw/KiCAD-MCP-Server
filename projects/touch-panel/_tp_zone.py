"""Would dropping GND's track mesh reopen the via gate?

_tp_dig.py settled what stops the CSELs: not the trace mask but `via_blocked`,
the second mask blocked_for() builds with the via's own radius.  Zeroing it
routes CSEL0 immediately (414 and 436 cells, against None), while ROW18 clears
it by 1,848 cells and succeeds.  On this board via_blocked covers 394,110 of
684,912 cells -- 57% -- because the panel has 2,939 tracks and *no* zones, so
every via site is within 0.46 mm of something.

The carrier's order is route-then-pour and the router ignores zones entirely
(absorb() reads only GetTracks()), so "delete the GND tracks, add a GND zone,
route, re-pour" is the architecture that would remove all of that by design
instead of by a surgical cut.  This measures whether it would actually help:
delete every GND track and via on a scratch board, rebuild the masks, and ask
the same two questions _tp_dig.py asked.

  python _tp_zone.py CSEL0,CSEL5,ROW18
"""
import os
import shutil
import sys

import numpy as np
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                      # noqa: E402

NETS = [n for n in (sys.argv[1] if len(sys.argv) > 1
                    else "CSEL0").split(",") if n]
PROBE = os.path.join(HERE, "_tp_zone.kicad_pcb")

shutil.copyfile(R.BOARD, PROBE)

# --- what is actually on the board, by net ----------------------------------
board = pcbnew.LoadBoard(R.BOARD)
seg = {}
via = {}
length = {}
for t in board.GetTracks():
    n = t.GetNetname()
    if isinstance(t, pcbnew.PCB_VIA):
        via[n] = via.get(n, 0) + 1
    else:
        seg[n] = seg.get(n, 0) + 1
        length[n] = length.get(n, 0.0) + (t.GetLength() / 1e6)
tot_s, tot_v = sum(seg.values()), sum(via.values())
print("board: %d segment(s), %d via(s), %d net(s) with copper"
      % (tot_s, tot_v, len(set(seg) | set(via))))
gnd_s, gnd_v = seg.get("GND", 0), via.get("GND", 0)
print("GND:   %d segment(s) (%.1f%%), %d via(s) (%.1f%%), %.1f mm of track"
      % (gnd_s, 100.0 * gnd_s / max(1, tot_s), gnd_v,
         100.0 * gnd_v / max(1, tot_v), length.get("GND", 0.0)))
top = sorted(seg, key=lambda n: -seg[n])[:8]
print("busiest nets: %s"
      % ", ".join("%s %d" % (n, seg[n]) for n in top))

# --- the same board with GND's copper gone ----------------------------------
board = pcbnew.LoadBoard(PROBE)
kill = [t for t in board.GetTracks() if t.GetNetname() == "GND"]
for t in kill:
    board.Remove(t)
board.Save(PROBE)
print("\ndeleted %d GND track(s) on the scratch board" % len(kill))

board = pcbnew.LoadBoard(PROBE)
rt = R.Router(board)
R.absorb(board, rt)

for NET in NETS:
    w = R.WIDTHS.get(NET, R.DEFAULT_W)
    hw = w / 2.0
    blocked, via_blocked = rt.blocked_for(NET, hw)
    pads = rt.pads.get(NET, [])
    print("\n=== %s  w=%.2f  %d pad(s)   (no GND copper on the board)"
          % (NET, w, len(pads)))
    if len(pads) < 2:
        print("    nothing to route")
        continue

    conn = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
    near = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
    for (onet, layer, x1, y1, x2, y2, ww) in rt.frozen:
        if onet == NET:
            R.raster_seg(conn, layer, x1, y1, x2, y2, ww / 2.0)
            R.raster_seg(near, layer, x1, y1, x2, y2, ww / 2.0 + R.GRID / 2.0)
    for (vnet, vx, vy) in rt.frozen_vias:
        if vnet == NET:
            for layer in (0, 1):
                R.raster_circle(conn, layer, vx, vy, R.VIA_D / 2.0)
                R.raster_circle(near, layer, vx, vy,
                                R.VIA_D / 2.0 + R.GRID / 2.0)
    _, _, n0, l0 = pads[0]
    for l in (l0 or (0, 1)):
        for (i, j) in n0:
            conn[l, i, j] = True
    seed = [(i, j, l) for l in (l0 or (0, 1)) for (i, j) in n0]
    reach = R.reachable(conn, seed, rt.via_ok)

    print("  blocked=%d  via_blocked=%d  reach=%d  of %d cell(s)"
          % (int(blocked.sum()), int(via_blocked.sum()), int(reach.sum()),
             R.NL * R.NX * R.NY))
    for k in range(1, len(pads)):
        _, _, nodes, layers = pads[k]
        starts = [(i, j, l) for l in (layers or (0, 1)) for (i, j) in nodes]
        p = rt.astar(blocked, via_blocked, starts, reach)
        print("     astar -> pad[%2d] (%8.3f,%8.3f): %s"
              % (k, pads[k][0], pads[k][1],
                 "None" if p is None else "%d cell(s)" % len(p)))

os.remove(PROBE)
