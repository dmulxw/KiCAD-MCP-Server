"""Where a vertical track can run, and how far.

The 21 ROW trunks all leave J1 at the bottom of the board and run up to their
row, so the scarce resource is *vertical corridor*. Counting how much of the
board's width can actually carry a full-height run says whether the trunks fit
at all, and -- when they do not -- exactly which x positions are the pinch
points.

Builds a clearance map on a grid: every other-net item is stamped into the
cells within its bounding box (grown by the clearance), so the cost is
proportional to the copper rather than to grid x items.

    python corridor-scan.py <board> <layer> [y0] [y1] [--step 0.1]
"""

import argparse
from array import array

import pcbnew

S = 1e6
TRACK_W = 0.2
CLEARANCE = 0.2
REACH = TRACK_W / 2 + CLEARANCE
FAR = 1e4


def layer_of(name):
    return pcbnew.F_Cu if name == "F.Cu" else pcbnew.B_Cu


def on_layer(item, layer):
    if isinstance(item, pcbnew.PAD):
        return item.IsOnLayer(layer)
    if isinstance(item, pcbnew.PCB_VIA):
        return True  # through via: blocks both copper layers
    if isinstance(item, pcbnew.PCB_TRACK):
        return item.IsOnLayer(layer)
    return False


def shapes(item):
    """Yield (ax, ay, bx, by, r, box) in mm for one piece of copper.

    ``box`` marks a filled rectangle. A pad is its bounding box, and measuring
    a point to a box's *diagonal* -- which is what the segment distance does
    with one -- leaves most of a 5mm touch pad reading as open copper.
    """
    if isinstance(item, pcbnew.PAD):
        bb = item.GetBoundingBox()
        yield (bb.GetLeft() / S, bb.GetTop() / S,
               bb.GetRight() / S, bb.GetBottom() / S, 0.0, True)
    elif isinstance(item, pcbnew.PCB_VIA):
        p = item.GetPosition()
        r = item.GetWidth() / S / 2
        yield (p.x / S - r, p.y / S - r, p.x / S + r, p.y / S + r, 0.0, True)
    elif isinstance(item, pcbnew.PCB_TRACK):
        s, e = item.GetStart(), item.GetEnd()
        yield (min(s.x, e.x) / S, min(s.y, e.y) / S,
               max(s.x, e.x) / S, max(s.y, e.y) / S,
               item.GetWidth() / S / 2, False)


def dist_seg(px, py, ax, ay, bx, by):
    if ax == bx and ay == by:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def dist_item(px, py, shape):
    ax, ay, bx, by, r, box = shape
    if box:
        dx = max(ax - px, 0.0, px - bx)
        dy = max(ay - py, 0.0, py - by)
        return (dx * dx + dy * dy) ** 0.5
    return dist_seg(px, py, ax, ay, bx, by) - r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("layer", choices=["F.Cu", "B.Cu"])
    ap.add_argument("y0", nargs="?", type=float)
    ap.add_argument("y1", nargs="?", type=float)
    ap.add_argument("--step", type=float, default=0.1)
    ap.add_argument("--min-run", type=float, default=20.0)
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    box = board.GetBoardEdgesBoundingBox()
    x0 = box.GetLeft() / S + 0.4
    x1 = box.GetRight() / S - 0.4
    y0 = a.y0 if a.y0 is not None else box.GetTop() / S + 1
    y1 = a.y1 if a.y1 is not None else box.GetBottom() / S - 1

    st = a.step
    nx = int((x1 - x0) / st) + 1
    ny = int((y1 - y0) / st) + 1
    clear = array("f", bytes(4 * nx * ny))
    for i in range(len(clear)):
        clear[i] = FAR

    lay = layer_of(a.layer)
    items = list(board.GetTracks())
    for fp in board.GetFootprints():
        items.extend(fp.Pads())

    stamped = 0
    for it in items:
        if not on_layer(it, lay):
            continue
        for shape in shapes(it):
            ax, ay, bx, by, r, box = shape
            reach = REACH if box else r + REACH
            i0 = max(0, int((ax - reach - x0) / st))
            i1 = min(nx - 1, int((bx + reach - x0) / st) + 1)
            j0 = max(0, int((ay - reach - y0) / st))
            j1 = min(ny - 1, int((by + reach - y0) / st) + 1)
            if i1 < i0 or j1 < j0:
                continue
            stamped += 1
            for i in range(i0, i1 + 1):
                px = x0 + i * st
                base = i * ny
                for j in range(j0, j1 + 1):
                    m = base + j
                    if clear[m] <= REACH:
                        continue
                    d = dist_item(px, y0 + j * st, shape)
                    if d < clear[m]:
                        clear[m] = d

    total = y1 - y0
    print(f"{a.layer}: {len(items)} items, {stamped} copper stamps, "
          f"grid {nx}x{ny}")
    print(f"a track centre needs >= {REACH:.2f}mm to other-net copper; "
          f"span {total:.0f}mm\n")

    rows = []
    for i in range(nx):
        base = i * ny
        best = cur = 0.0
        nfree = 0
        for j in range(ny):
            if clear[base + j] >= REACH:
                nfree += 1
                cur += st
                if cur > best:
                    best = cur
            else:
                cur = 0.0
        rows.append((x0 + i * st, nfree * st, best))

    printable = [r for r in rows if r[2] >= a.min_run]
    print(f"{'x':>8} {'free':>8} {'longest':>8}  <- runs >= {a.min_run:.0f}mm")
    for x, free, run in printable:
        print(f"{x:8.2f} {free:8.1f} {run:8.1f}")

    full = [r for r in rows if r[2] >= total - 1.0]
    print(f"\n{len(full)} x position(s) free over the whole span:")
    for x, free, run in full:
        print(f"  x={x:7.2f}  free {free:.1f}mm  longest {run:.1f}mm")


if __name__ == "__main__":
    main()
