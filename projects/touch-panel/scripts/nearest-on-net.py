"""Nearest copper of a net to a point -- how far an island is from its break.

`find-open-nets.py` says which nets are split and what each island holds, but
not how far apart the islands are. That distance decides whether the gap can be
bridged by hand or needs the router: a few millimetres is a track, a hundred is
a re-route.

    python nearest-on-net.py <board> <net> <x_mm> <y_mm> [n]
"""

import sys

import pcbnew

SCALE = 1e6


def dist_to_item(item, px, py):
    """Shortest distance in mm from (px,py) to the item's copper."""
    if isinstance(item, pcbnew.PAD):
        p = item.GetPosition()
        return ((p.x / SCALE - px) ** 2 + (p.y / SCALE - py) ** 2) ** 0.5
    if isinstance(item, pcbnew.PCB_VIA):
        p = item.GetPosition()
        return (((p.x / SCALE - px) ** 2 + (p.y / SCALE - py) ** 2) ** 0.5
                - item.GetWidth() / SCALE / 2)
    if isinstance(item, pcbnew.PCB_TRACK):
        ax, ay = item.GetStart().x / SCALE, item.GetStart().y / SCALE
        bx, by = item.GetEnd().x / SCALE, item.GetEnd().y / SCALE
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
            t = max(0.0, min(1.0, t))
            d = ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5
        return d - item.GetWidth() / SCALE / 2
    return None


def describe(item):
    if isinstance(item, pcbnew.PAD):
        return f"pad {item.GetParentFootprint().GetReference()}.{item.GetNumber()}"
    if isinstance(item, pcbnew.PCB_VIA):
        return f"via @ {item.GetPosition().x/SCALE:.4f},{item.GetPosition().y/SCALE:.4f}"
    if isinstance(item, pcbnew.PCB_TRACK):
        s, e = item.GetStart(), item.GetEnd()
        return (f"track {s.x/SCALE:.4f},{s.y/SCALE:.4f} -> "
                f"{e.x/SCALE:.4f},{e.y/SCALE:.4f} len={item.GetLength()/SCALE:.3f}")
    return "?"


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    want, px, py = sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 6

    hits = []
    for t in board.GetTracks():
        if t.GetNetname() != want:
            continue
        d = dist_to_item(t, px, py)
        if d is not None:
            hits.append((d, t))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != want:
                continue
            d = dist_to_item(pad, px, py)
            if d is not None:
                hits.append((d, pad))

    hits.sort(key=lambda h: h[0])
    print(f"nearest copper on net {want} to ({px}, {py}):")
    for d, item in hits[:n]:
        print(f"  {d:8.3f} mm  {describe(item)}")


if __name__ == "__main__":
    main()
