"""Show the modelled distance next to the true distance, per obstacle.

probe.item_shape() returns a track's bounding-box corners, and probe.NGrid
.feed() runs those straight into _seg_dist().  For an axis-aligned track the
bbox corners ARE the endpoints, so the field is exact; for a diagonal track they
are the *anti*-diagonal, so the field measures a segment that is not on the
board.  This prints, for the cells the DRC flagged, every obstacle within R and
both distances -- modelled (what astar saw) and true (what DRC sees).
"""
import sys, os, math
sys.path.insert(0, os.getcwd())
import pcbnew
import emitlib as M
import probe
from probe import item_shape

S = 1e6
board = pcbnew.LoadBoard(os.environ.get("SRC", "_r1.kicad_pcb"))
M.bind(board, st=0.1)
R = float(os.environ.get("R", "6.0"))

CASES = [
    ("ROW9", 100.55, 158.75, "ROW5"),
    ("ROW1", 102.35, 128.25, "ROW16"),
    ("ROW2", 102.95, 127.95, "ROW16"),
    ("CSEL8", 168.65, 233.45, "GND"),
]


def true_dist(it, px, py):
    """Distance to the copper as KiCad sees it -- real endpoints for tracks."""
    if isinstance(it, pcbnew.PAD) or isinstance(it, pcbnew.PCB_VIA):
        bb = it.GetBoundingBox()
        dx = max(bb.GetLeft() / S - px, 0.0, px - bb.GetRight() / S)
        dy = max(bb.GetTop() / S - py, 0.0, py - bb.GetBottom() / S)
        return math.hypot(dx, dy)
    s, e = it.GetStart(), it.GetEnd()
    d = float(probe.NGrid._seg_dist(px, py, s.x / S, s.y / S,
                                    e.x / S, e.y / S))
    return d - it.GetWidth() / S / 2


def fmt(it):
    if isinstance(it, pcbnew.PAD):
        c = it.GetPosition()
        return "PAD  %-8s %-5s (%.3f,%.3f)" % (it.GetNetname(),
                                               it.GetParent().GetReference(),
                                               c.x / S, c.y / S)
    s, e = it.GetStart(), it.GetEnd()
    kind = "VIA" if isinstance(it, pcbnew.PCB_VIA) else "TRK"
    return ("%-4s %-8s lay=%d (%.3f,%.3f)->(%.3f,%.3f)"
            % (kind, it.GetNetname(), it.GetLayer(),
               s.x / S, s.y / S, e.x / S, e.y / S))


for net, px, py, other in CASES:
    obstacles = [it for it in M.fresh() if it.GetNetname() != net]
    print("=" * 78)
    print("%s at (%.3f, %.3f)   (DRC pairs it with %s)" % (net, px, py, other))
    rows = []
    for it in obstacles:
        sh = item_shape(it)
        if sh is None:
            continue
        ax, ay, bx, by, r, box = sh
        if box:
            dx = max(ax - px, 0.0, px - bx)
            dy = max(ay - py, 0.0, py - by)
            dm = math.hypot(dx, dy)
        else:
            dm = float(probe.NGrid._seg_dist(px, py, ax, ay, bx, by)) - r
        dt = true_dist(it, px, py)
        rows.append((dt, dm, it))
    rows.sort(key=lambda z: z[0])
    print("   %-8s %-8s  %s" % ("TRUE", "MODELLED", "item"))
    for dt, dm, it in rows[:4]:
        flag = "   <-- WRONG" if dm - dt > 0.2 else ""
        print("   %8.4f %8.4f  %s%s" % (dt, dm, fmt(it), flag))
    nb = min(dm for _, dm, _ in rows)
    nt = min(dt for dt, _, _ in rows)
    print("   nearest: true %.4f  modelled %.4f   (keep=%.2f)  %s"
          % (nt, nb, M.keep, "SHORT -- grid said legal" if nt < 0.1 else ""))
