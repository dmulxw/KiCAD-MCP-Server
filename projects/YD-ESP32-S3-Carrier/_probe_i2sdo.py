"""Why can I2S_DO not reach J1.6, and IO38 not reach J2.10?

Both are pads that moved with their header, and both stall on the first round and
every repair round after it -- which is the signature of an obstruction the repair
loop cannot lift.  rip() only touches router.tracks / router.vias; the board's
pre-existing copper lives in router.frozen and is untouchable.  So print, around
each stalled pad, what is actually sitting there and who owns it.

  python _probe_i2sdo.py [board.kicad_pcb]
"""
import sys

import pcbnew

BOARD = sys.argv[1] if len(sys.argv) > 1 else (
    r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\_v90.kicad_pcb")

# The two stall points, straight out of route_all()'s diagnostics.
STALLS = {"I2S_DO": (11.0, 31.5), "IO38": (36.4, 41.66)}

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)

TO = pcbnew.ToMM


def owners(x, y, r):
    """Everything with copper within r of (x, y), as (kind, net, who, dist)."""
    out = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            px, py = TO(p.x), TO(p.y)
            d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            if d <= r:
                out.append(("via", str(t.GetNetname()), "-", d, px, py,
                            TO(t.GetWidth(pcbnew.F_Cu))))
            continue
        s, e = t.GetStart(), t.GetEnd()
        sx, sy, ex, ey = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
        dx, dy = ex - sx, ey - sy
        L2 = dx * dx + dy * dy
        tpar = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - sx) * dx + (y - sy) * dy) / L2))
        cx, cy = sx + tpar * dx, sy + tpar * dy
        d = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
        if d <= r:
            out.append(("trk", str(t.GetNetname()),
                        board.GetLayerName(t.GetLayer()), d, cx, cy,
                        TO(t.GetWidth())))
    return out


print("=== board pad column at the stall points ===")
for ref in ("J1", "J2"):
    fp = board.FindFootprintByReference(ref)
    ps = sorted(fp.Pads(), key=lambda p: int(str(p.GetNumber())))
    near = [p for p in ps if abs(TO(p.GetPosition().y) - 31.5) < 15]
    print("  %s at (%.2f,%.2f) rot %.0f, %d pads" %
          (ref, TO(fp.GetPosition().x), TO(fp.GetPosition().y),
           fp.GetOrientationDegrees(), len(ps)))
    for p in near:
        pos = p.GetPosition()
        b = p.GetBoundingBox()
        print("    pad %-3s (%.3f,%.3f)  net %-8s  %.2f x %.2f  layers=%s" %
              (str(p.GetNumber()), TO(pos.x), TO(pos.y), str(p.GetNetname()),
               TO(b.GetWidth()), TO(b.GetHeight()),
               ",".join(board.GetLayerName(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)
                        if p.IsOnLayer(l))))

for net, (x, y) in sorted(STALLS.items()):
    print("\n=== %s: copper within 6 mm of the stalled pad (%.2f,%.2f) ===" % (net, x, y))
    rows = sorted(owners(x, y, 6.0), key=lambda r: r[3])
    for (kind, onet, who, d, px, py, w) in rows[:34]:
        tag = "  <== SAME NET" if onet == net else ""
        print("  %-3s %-8s %-6s d=%5.2f  at (%7.3f,%7.3f)  w=%.2f%s" %
              (kind, onet, who, d, px, py, w, tag))
    print("  %d item(s) within 6 mm" % len(rows))
