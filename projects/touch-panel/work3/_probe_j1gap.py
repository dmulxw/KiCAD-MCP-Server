"""How thick is the wall around the J1.4 / J1.6 bay, and where is ROW3/ROW5?

The flood (both models) says the bay x~124.9-128.9, y 241.4-248.5 (pad 4) is
enclosed by other rows' fan-out.  Whether that is recoverable depends on one
number: the straight-line distance from the bay to the target net's own copper.
A few tenths of a millimetre of one foreign segment is a rip; a weave of seven
nets is a re-plan.

    python _probe_j1gap.py
"""
import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew

S = 1e6
board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')

# bay measured by _probe_j1wall.py, padded by 0.15mm
BAY = (124.70, 241.30, 129.05, 248.60)


def seg_pt_dist(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def near_box(bb, pad=0.0):
    return not (bb.GetRight() / S < BAY[0] - pad or bb.GetLeft() / S > BAY[2] + pad
                or bb.GetBottom() / S < BAY[1] - pad or bb.GetTop() / S > BAY[3] + pad)


for pinnum, netname in (("4", "ROW3"), ("6", "ROW5")):
    print("\n===== J1.%s  target %s" % (pinnum, netname), flush=True)

    # nearest piece of the target net's own copper, walking outward
    best = None
    for t in board.GetTracks():
        if t.GetNetname() != netname:
            continue
        for end in (t.GetStart(), t.GetEnd()):
            px, py = end.x / S, end.y / S
            cx = min(max(px, BAY[0]), BAY[2])
            cy = min(max(py, BAY[1]), BAY[3])
            d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            if best is None or d < best[0]:
                best = (d, t, px, py)
    if best:
        d, t, px, py = best
        print("  nearest %s copper: %.2f mm at (%.3f, %.3f) on %s  [%.3f,%.3f -> %.3f,%.3f]"
              % (netname, d, px, py, t.GetLayerName(),
                 t.GetStart().x / S, t.GetStart().y / S,
                 t.GetEnd().x / S, t.GetEnd().y / S), flush=True)
    else:
        print("  no %s copper at all" % netname, flush=True)

    # what sits in the 1.6mm band around the bay, per net
    band = {}
    for t in board.GetTracks():
        if not near_box(t.GetBoundingBox(), 1.6):
            continue
        nm = t.GetNetname() or "<none>"
        e = band.setdefault(nm, [0, 1e9])
        e[0] += 1
        for end in (t.GetStart(), t.GetEnd()):
            px, py = end.x / S, end.y / S
            cx = min(max(px, BAY[0]), BAY[2])
            cy = min(max(py, BAY[1]), BAY[3])
            e[1] = min(e[1], ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5)
    print("  band +-1.6mm (%d nets):" % len(band), flush=True)
    for nm, (n, d) in sorted(band.items(), key=lambda kv: kv[1][1]):
        print("     %-8s %3d seg  nearest %.2f mm" % (nm, n, d), flush=True)
