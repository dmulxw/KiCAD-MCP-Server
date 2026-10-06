"""Which copper is actually sitting on the two stalled pads -- and did it get
there before or after the router ran?

The closest-point readout in _probe_i2sdo.py hides the track's extent: a long run
that merely passes x = 36.4 reports as if it were a dot there.  So print whole
segments, and compare the moved-but-unrouted board against the routed one, so
each item is labelled FROZEN (was there already) or NEW (the router laid it).

If the seal is NEW, the router is laying a foreign trace straight over a pad --
it should not, blocked_for() rasterises every foreign pad into `shapes` -- and the
bug is on our side.  If the seal is FROZEN, it is old copper sitting where the pad
has moved to, which no amount of ripping can lift and the layout has to change.

  python _probe_stall2.py
"""
import sys

import pcbnew

BASE = (r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier")
TO = pcbnew.ToMM


def grab(path):
    """(segments, vias) as dicts, keyed by geometry."""
    board = pcbnew.LoadBoard(path)
    if board is None:
        sys.exit("LoadBoard returned None for " + path)
    segs, vias = {}, {}
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            vias[(str(t.GetNetname()), round(TO(p.x), 3), round(TO(p.y), 3))] = \
                TO(t.GetWidth(pcbnew.F_Cu))
            continue
        s, e = t.GetStart(), t.GetEnd()
        a = (str(t.GetNetname()), t.GetLayer(),
             round(TO(s.x), 3), round(TO(s.y), 3),
             round(TO(e.x), 3), round(TO(e.y), 3), round(TO(t.GetWidth()), 3))
        segs[a] = segs.get(a, 0) + 1
    return board, segs, vias


board, new_segs, new_vias = grab(BASE + r"\_v90.kicad_pcb")
_, old_segs, old_vias = grab(BASE + r"\_v90_pre.kicad_pcb")

# The stalled pads and the copper that reaches into them.  A 1.70 mm pad has a
# 0.85 mm half-size, so anything whose centre is inside that is on the pad.
STALLS = {"I2S_DO": (11.0, 31.5, 6), "IO38": (36.4, 41.66, 10)}


def near(segs, x, y, r):
    """Segments whose centreline comes within r of (x, y)."""
    for (net, layer, x1, y1, x2, y2, w) in segs:
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        cx, cy = x1 + t * dx, y1 + t * dy
        d = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
        if d <= r:
            yield (d, net, layer, x1, y1, x2, y2, w)


for net, (x, y, hw) in sorted(STALLS.items()):
    print("=== %s stalled at (%.2f, %.2f) -- pad half-size %.2f mm ===" % (net, x, y, hw))
    rows = [r for r in near(new_segs, x, y, hw + 0.15) if r[1] != net]
    print("  %d foreign segment(s) crossing the pad itself:" % len(rows))
    for (d, onet, layer, x1, y1, x2, y2, w) in sorted(rows):
        tag = "FROZEN" if (onet, layer, x1, y1, x2, y2, w) in old_segs else "NEW"
        print("    %-6s %-12s %-5s (%7.3f,%7.3f)-(%7.3f,%7.3f) w=%.2f  d=%.2f"
              % (tag, onet, board.GetLayerName(layer), x1, y1, x2, y2, w, d))

    print("  every foreign segment within %.1f mm (FROZEN = pre-router):" % (hw + 1.5))
    for (d, onet, layer, x1, y1, x2, y2, w) in sorted(near(new_segs, x, y, hw + 1.5))[:18]:
        if onet == net:
            continue
        tag = "FROZEN" if (onet, layer, x1, y1, x2, y2, w) in old_segs else "NEW"
        print("    %-6s %-12s %-5s (%7.3f,%7.3f)-(%7.3f,%7.3f) w=%.2f  d=%.2f"
              % (tag, onet, board.GetLayerName(layer), x1, y1, x2, y2, w, d))
    print()

print("=== vias that are new vs frozen, board-wide ===")
print("  frozen vias %d, total %d, so %d laid by this run"
      % (len(old_vias), len(new_vias), len(new_vias) - len(old_vias)))
print("  frozen segs %d, total %d" % (sum(old_segs.values()), sum(new_segs.values())))
