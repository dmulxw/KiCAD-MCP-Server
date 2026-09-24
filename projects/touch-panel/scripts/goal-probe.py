"""Why a net's A* search cannot reach the pads it is aiming at.

`route-open-nets.py` reports NO PATH FOUND after expanding millions of cells,
which is ambiguous: either the target pads are sealed in their own corner of
the board, or the goal cells themselves fail the legality test and so can
never be entered. This prints, per own-net item, the distance from its centre
to the nearest other-net copper and the board-edge gap, against the two
thresholds the search applies.

    python goal-probe.py <board> <net> [--clearance 0.2] [--safety 0.0]
"""

import argparse

import pcbnew

S = 1e6
TRACK_W = 0.2
VIA_DIA = 0.6


def on_layer(item, layer):
    if isinstance(item, pcbnew.PAD):
        return item.IsOnLayer(layer)
    if isinstance(item, pcbnew.PCB_VIA):
        return True
    if isinstance(item, pcbnew.PCB_TRACK):
        return item.IsOnLayer(layer)
    return False


def dist_to(item, px, py):
    """Distance in mm from a point to one item's copper."""
    if isinstance(item, pcbnew.PAD):
        bb = item.GetBoundingBox()
        nx = min(max(px, bb.GetLeft() / S), bb.GetRight() / S)
        ny = min(max(py, bb.GetTop() / S), bb.GetBottom() / S)
        return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5
    if isinstance(item, pcbnew.PCB_VIA):
        p = item.GetPosition()
        r = item.GetWidth() / S / 2
        return ((px - p.x / S) ** 2 + (py - p.y / S) ** 2) ** 0.5 - r
    if isinstance(item, pcbnew.PCB_TRACK):
        ax, ay = item.GetStart().x / S, item.GetStart().y / S
        bx, by = item.GetEnd().x / S, item.GetEnd().y / S
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        else:
            t = max(0.0, min(1.0,
                            ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            d = ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5
        return d - item.GetWidth() / S / 2
    return None


def label(item):
    if isinstance(item, pcbnew.PAD):
        return f"pad {item.GetParentFootprint().GetReference()}.{item.GetNumber()}"
    return item.GetClass()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("net")
    ap.add_argument("--clearance", type=float, default=0.2)
    ap.add_argument("--safety", type=float, default=0.0)
    a = ap.parse_args()

    keep = a.clearance + TRACK_W / 2 + a.safety
    board = pcbnew.LoadBoard(a.board)
    bb = board.GetBoardEdgesBoundingBox()
    bx0, by0 = bb.GetLeft() / S, bb.GetTop() / S
    bx1, by1 = bb.GetRight() / S, bb.GetBottom() / S

    others = [t for t in board.GetTracks() if t.GetNetname() != a.net]
    own = [t for t in board.GetTracks() if t.GetNetname() == a.net]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            (own if pad.GetNetname() == a.net else others).append(pad)

    print(f"net {a.net}: {len(own)} own item(s), {len(others)} other-net item(s)")
    print(f"a track centre needs >= {keep:.3f}mm to other-net copper\n")

    for it in own:
        s = it.GetBoundingBox()
        cx = (s.GetLeft() + s.GetRight()) / 2 / S
        cy = (s.GetTop() + s.GetBottom()) / 2 / S
        layers = [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if on_layer(it, l)]
        gaps = []
        for o in others:
            for l in layers:
                if not on_layer(o, l):
                    continue
                d = dist_to(o, cx, cy)
                if d is not None:
                    gaps.append(d)
        worst = min(gaps) if gaps else float("inf")
        e = min(cx - bx0, bx1 - cx, cy - by0, by1 - cy)
        ok = "ok  " if worst >= keep else "SEAL"
        print(f"  {ok} {label(it):<24} centre ({cx:7.2f},{cy:7.2f})  "
              f"nearest other-net copper {worst:6.3f}mm  edge {e:6.2f}mm  "
              f"layers {[board.GetLayerName(l) for l in layers]}")


if __name__ == "__main__":
    main()
