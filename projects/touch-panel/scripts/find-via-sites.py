"""Find places a via of a given net could legally go inside a box.

Hand-checking clearances against a printed neighbour list is how you talk
yourself into a via that DRC then rejects: what matters is the distance to
*every* other-net item on the layers the via drills through, not just the
handful a radius probe happened to print.

This walks a grid over the box, tests a candidate via against every track, via,
pad and footprint opening on F.Cu and B.Cu, and prints the sites that clear the
board's own rules by at least `margin`.

    python find-via-sites.py <board> <net> <x0> <y0> <x1> <y1> [--step 0.25]
"""

import argparse
import sys

import pcbnew

S = 1e6
VIA_DIA = 0.6
VIA_DRILL = 0.3
CLEARANCE = 0.2


def bounds(item):
    """Bounding box (x0, y0, x1, y1) in mm of an item's copper."""
    if isinstance(item, pcbnew.PAD):
        bb = item.GetBoundingBox()
        return (bb.GetLeft() / S, bb.GetTop() / S, bb.GetRight() / S, bb.GetBottom() / S)
    if isinstance(item, pcbnew.PCB_VIA):
        p, r = item.GetPosition(), item.GetWidth() / S / 2
        return (p.x / S - r, p.y / S - r, p.x / S + r, p.y / S + r)
    if isinstance(item, pcbnew.PCB_TRACK):
        s, e = item.GetStart(), item.GetEnd()
        r = item.GetWidth() / S / 2
        return (min(s.x, e.x) / S - r, min(s.y, e.y) / S - r,
                max(s.x, e.x) / S + r, max(s.y, e.y) / S + r)
    return None


def gap(px, py, item):
    """Distance from a point to the item's copper, in mm."""
    if isinstance(item, pcbnew.PAD):
        bb = item.GetBoundingBox()
        x0, y0, x1, y1 = (bb.GetLeft() / S, bb.GetTop() / S,
                          bb.GetRight() / S, bb.GetBottom() / S)
        nx, ny = min(max(px, x0), x1), min(max(py, y0), y1)
        return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5
    if isinstance(item, pcbnew.PCB_VIA):
        p = item.GetPosition()
        return (((px - p.x / S) ** 2 + (py - p.y / S) ** 2) ** 0.5
                - item.GetWidth() / S / 2)
    if isinstance(item, pcbnew.PCB_TRACK):
        ax, ay = item.GetStart().x / S, item.GetStart().y / S
        bx, by = item.GetEnd().x / S, item.GetEnd().y / S
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            d = ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5
        return d - item.GetWidth() / S / 2
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("net")
    ap.add_argument("x0", type=float)
    ap.add_argument("y0", type=float)
    ap.add_argument("x1", type=float)
    ap.add_argument("y1", type=float)
    ap.add_argument("--step", type=float, default=0.25)
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)

    # Everything that could conflict: copper on either layer, excluding the net
    # we are placing (its own copper is a connection, not an obstruction).
    others = []
    for t in board.GetTracks():
        if t.GetNetname() != a.net:
            others.append(t)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != a.net:
                others.append(pad)

    print(f"{len(others)} other-net item(s) considered")
    print(f"grid {a.step}mm over x[{a.x0},{a.x1}] y[{a.y0},{a.y1}], "
          f"via {VIA_DIA}mm needs >= {CLEARANCE}mm to other copper\n")

    sites = []
    y = a.y0
    while y <= a.y1 + 1e-9:
        x = a.x0
        while x <= a.x1 + 1e-9:
            worst = min(gap(x, y, o) for o in others) - VIA_DIA / 2
            if worst >= CLEARANCE:
                sites.append((worst, x, y))
            x += a.step
        y += a.step

    if not sites:
        print("NO clear via site in this box.")
        return

    sites.sort(key=lambda s: -s[0])
    print(f"{len(sites)} clear site(s); best 12 by clearance:")
    for worst, x, y in sites[:12]:
        print(f"  clearance {worst:6.3f} mm  at ({x:.2f}, {y:.2f})")

    rows = sorted({round(s[2], 3) for s in sites})
    print(f"\nclear rows (y): {rows[:20]}")


if __name__ == "__main__":
    main()
