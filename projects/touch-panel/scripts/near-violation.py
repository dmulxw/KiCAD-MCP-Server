"""List board items close to a point, to identify an unexplained DRC clearance.

The MCP `get_drc_violations` result carries only a message and a location --
no indication of *which* two objects are too close. This prints every track,
via, pad and footprint courtyard edge within a radius of the given point so
the pair can be identified by eye.

    python near-violation.py <board> <x_mm> <y_mm> [radius_mm]
"""
import sys
import pcbnew

scale = 1_000_000.0


def fmt(v):
    return f"({v.x / scale:.4f}, {v.y / scale:.4f})"


def seg_point_distance(px, py, ax, ay, bx, by):
    """Shortest distance from (px,py) to the segment (ax,ay)-(bx,by), in mm."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def main():
    board_path, px, py = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    radius = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    board = pcbnew.LoadBoard(board_path)

    hits = []

    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            d = ((t.GetPosition().x / scale - px) ** 2
                 + (t.GetPosition().y / scale - py) ** 2) ** 0.5
            d -= t.GetWidth() / scale / 2
            hits.append((d, "via", f"net={t.GetNetname()} dia={t.GetWidth()/scale} drill={t.GetDrillValue()/scale} @ {fmt(t.GetPosition())}"))
        else:
            s, e = t.GetStart(), t.GetEnd()
            d = seg_point_distance(px, py, s.x / scale, s.y / scale, e.x / scale, e.y / scale)
            d -= t.GetWidth() / scale / 2
            hits.append((d, "track", f"net={t.GetNetname()} w={t.GetWidth()/scale} layer={board.GetLayerName(t.GetLayer())} {fmt(s)}-{fmt(e)}"))

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            d = ((pos.x / scale - px) ** 2 + (pos.y / scale - py) ** 2) ** 0.5
            d -= max(pad.GetSize().x, pad.GetSize().y) / scale / 2
            hits.append((d, "pad", f"{fp.GetReference()} pad={pad.GetNumber()} net={pad.GetNetname()} size={pad.GetSize().x/scale}x{pad.GetSize().y/scale} @ {fmt(pos)}"))
        for g in fp.GraphicalItems():
            if g.GetLayer() != pcbnew.F_CrtYd:
                continue
            bb = g.GetBoundingBox()
            x0, y0 = bb.GetLeft() / scale, bb.GetTop() / scale
            x1, y1 = bb.GetRight() / scale, bb.GetBottom() / scale
            if x0 <= px <= x1 and y0 <= py <= y1:
                hits.append((0.0, "courtyard", f"{fp.GetReference()} cx {x0:.3f}..{x1:.3f} cy {y0:.3f}..{y1:.3f}"))

    hits.sort(key=lambda h: h[0])
    print(f"items within {radius}mm of ({px}, {py}):")
    for d, kind, desc in hits:
        if d > radius:
            continue
        print(f"  gap {d:8.4f}  {kind:10s} {desc}")


if __name__ == "__main__":
    main()
