"""Like find-open-nets.py, but always prints the nearest gap and the pair.

find-open-nets.py only reports gaps under 20mm, which hides the case this
board is in: the connector-side stub is a long way from the matrix routing.
This prints, per island pair, the closest two items and their separation.

    docker run --rm -v D:/source/repos/KiCAD-MCP-Server:/workspace \
        -w /workspace kicad-mcp:9.0 \
        /opt/kicad-mcp-venv/bin/python .scratch/gap-detail.py
"""

import importlib.util
import math
import sys

import pcbnew

SRC = "/workspace/projects/touch-panel/scripts/find-open-nets.py"
BOARD = "/workspace/projects/touch-panel/touch-panel.kicad_pcb"


def load_helpers():
    spec = importlib.util.spec_from_file_location("fon", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def item_point(item):
    if isinstance(item, pcbnew.PAD):
        p = item.GetPosition()
        return (p.x / 1e6, p.y / 1e6)
    if isinstance(item, pcbnew.PCB_TRACK):
        p = item.GetPosition()
        return (p.x / 1e6, p.y / 1e6)
    return None


def seg_seg_distance(a, b):
    """Shortest distance between two track segments, in mm."""
    (ax, ay), (bx, by) = _ends(a)
    (cx, cy), (dx, dy) = _ends(b)
    best = min(
        _pt_seg(ax, ay, cx, cy, dx, dy),
        _pt_seg(bx, by, cx, cy, dx, dy),
        _pt_seg(cx, cy, ax, ay, bx, by),
        _pt_seg(dx, dy, ax, ay, bx, by),
    )
    return best - (a.GetWidth() + b.GetWidth()) / 2e6


def _ends(t):
    s, e = t.GetStart(), t.GetEnd()
    return (s.x / 1e6, s.y / 1e6), (e.x / 1e6, e.y / 1e6)


def _pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def pad_to_pt(pad):
    return item_point(pad)


def closest(a_items, b_items):
    """Nearest pair across two islands, as (distance_mm, item_a, item_b)."""
    best = None
    for a in a_items:
        pa = item_point(a)
        if pa is None:
            continue
        for b in b_items:
            if isinstance(a, pcbnew.PCB_TRACK) and isinstance(b, pcbnew.PCB_TRACK):
                d = seg_seg_distance(a, b)
            else:
                pb = item_point(b)
                if pb is None:
                    continue
                d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                if isinstance(a, pcbnew.PAD):
                    d -= _pad_radius(a)
                if isinstance(b, pcbnew.PAD):
                    d -= _pad_radius(b)
            if best is None or d < best[0]:
                best = (d, a, b)
    return best


def _pad_radius(pad):
    try:
        sz = pad.GetSize()
        return min(sz.x, sz.y) / 2e6
    except Exception:
        return 0.0


def main():
    fon = load_helpers()
    board = pcbnew.LoadBoard(BOARD)
    board.BuildConnectivity()

    nets = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() > 0:
                nets.setdefault(pad.GetNetCode(), []).append(pad)
    for track in board.GetTracks():
        if track.GetNetCode() > 0:
            nets.setdefault(track.GetNetCode(), []).append(track)

    for code, items in sorted(nets.items()):
        name = board.FindNet(code).GetNetname()
        groups = fon._components(items)
        if len(groups) <= 1:
            continue
        groups = sorted(groups, key=len, reverse=True)
        print(f"\n=== {name}  ({len(groups)} islands, sizes "
              f"{[len(g) for g in groups]})")
        for gi, g in enumerate(groups):
            pts = [item_point(i) for i in g]
            pts = [p for p in pts if p]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            print(f"  island {gi}: {len(g)} items, "
                  f"bbox X {min(xs):.2f}..{max(xs):.2f} "
                  f"Y {min(ys):.2f}..{max(ys):.2f}")
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                r = closest(groups[a], groups[b])
                if r is None:
                    continue
                d, ia, ib = r
                print(f"  gap {a}<->{b}: {d:.3f} mm")
                print(f"      {fon.label(ia)}")
                print(f"      {fon.label(ib)}")


if __name__ == "__main__":
    sys.exit(main() or 0)
