#!/usr/bin/env python3
"""Report which nets are not fully connected, and where the break is.

`kicad-cli pcb drc` says "Found 7 unconnected items" and names the first pair of
items it finds on each net, but that pair is arbitrary -- it does not say where
the copper actually stops. This walks the board's own connectivity model and,
for every net with more than one connected island, prints the islands and the
shortest gap between them.

Run inside the image:

    docker run --rm -v D:/source/repos/KiCAD-MCP-Server:/workspace \
        -w /workspace kicad-mcp:9.0 \
        /opt/kicad-mcp-venv/bin/python \
        projects/touch-panel/scripts/find-open-nets.py
"""

import math
import sys

import pcbnew

BOARD = "/workspace/projects/touch-panel/touch-panel.kicad_pcb"


def item_point(item):
    """A representative (x, y) in mm for a board item, or None."""
    if isinstance(item, pcbnew.PAD):
        p = item.GetPosition()
        return (p.x / 1e6, p.y / 1e6)
    if isinstance(item, (pcbnew.PCB_TRACK, pcbnew.PCB_VIA)):
        p = item.GetPosition()
        return (p.x / 1e6, p.y / 1e6)
    if isinstance(item, pcbnew.FOOTPRINT):
        p = item.GetPosition()
        return (p.x / 1e6, p.y / 1e6)
    return None


def label(item):
    if isinstance(item, pcbnew.PAD):
        return f"{item.GetParentFootprint().GetReference()}.{item.GetNumber()}"
    if isinstance(item, pcbnew.PCB_VIA):
        p = item.GetPosition()
        return f"via@({p.x / 1e6:.2f},{p.y / 1e6:.2f})"
    if isinstance(item, pcbnew.PCB_TRACK):
        s, e = item.GetStart(), item.GetEnd()
        return (f"track ({s.x / 1e6:.2f},{s.y / 1e6:.2f})"
                f"->({e.x / 1e6:.2f},{e.y / 1e6:.2f})")
    return repr(item)


def main():
    board = pcbnew.LoadBoard(BOARD)
    board.BuildConnectivity()
    conn = board.GetConnectivity()

    nets = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            code = pad.GetNetCode()
            if code > 0:
                nets.setdefault(code, []).append(pad)
    for track in board.GetTracks():
        code = track.GetNetCode()
        if code > 0:
            nets.setdefault(code, []).append(track)

    open_nets = []
    for code, items in sorted(nets.items()):
        nname = board.FindNet(code).GetNetname()
        # pcbnew's own island query (CONNECTIVITY_DATA::GetRatsnestForNet) is not
        # exposed through SWIG, so group the items geometrically instead.
        groups = _components(items)
        if len(groups) <= 1:
            continue
        open_nets.append((nname, groups))

    if not open_nets:
        print("every net is a single connected island")
        return 0

    print(f"{len(open_nets)} net(s) with more than one island\n")
    for nname, groups in open_nets:
        groups = sorted(groups, key=len, reverse=True)
        print(f"{nname}: {len(groups)} islands")
        for gi, g in enumerate(groups):
            shown = ", ".join(label(i) for i in g[:4])
            more = f" (+{len(g) - 4})" if len(g) > 4 else ""
            print(f"    island {gi} [{len(g)} item(s)]: {shown}{more}")
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                d = _gap(groups[a], groups[b])
                if d is not None and d < 20:
                    print(f"    nearest gap island {a} <-> {b}: {d:.3f} mm")
        print()
    return 1


def _components(items):
    """Group items that physically touch, using KiCad's own hit testing.

    Endpoint coincidence is not enough on its own: KiCad splits a route at every
    corner and at every pad it crosses, and a T-junction leaves one segment's
    endpoint in the middle of another. Two items are joined here when a test
    point of one lies on the other, which covers all three cases.
    """
    parent = list(range(len(items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    probes = [_probes(i) for i in items]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _touches(items[i], probes[i], items[j], probes[j]):
                union(i, j)

    out = {}
    for i in range(len(items)):
        out.setdefault(find(i), []).append(items[i])
    return list(out.values())


def _probes(item):
    """Test points on an item: its endpoints, plus its centre."""
    if isinstance(item, pcbnew.PCB_TRACK):
        s, e = item.GetStart(), item.GetEnd()
        pts = [(s.x / 1e6, s.y / 1e6), (e.x / 1e6, e.y / 1e6)]
        if isinstance(item, pcbnew.PCB_VIA):
            c = item.GetPosition()
            pts.append((c.x / 1e6, c.y / 1e6))
        return pts
    p = item_point(item)
    return [p] if p else []


def _touches(a, pa, b, pb):
    """True if a and b overlap in copper."""
    if isinstance(a, pcbnew.PCB_TRACK) and isinstance(b, pcbnew.PCB_TRACK):
        if not _share_layer(a, b):
            return False
        return _segments_touch(a, b) or _segments_touch(b, a)
    if isinstance(a, pcbnew.PAD) and isinstance(b, pcbnew.PCB_TRACK):
        return _pad_touches_track(a, b)
    if isinstance(b, pcbnew.PAD) and isinstance(a, pcbnew.PCB_TRACK):
        return _pad_touches_track(b, a)
    return False


def _share_layer(a, b):
    """True if two tracked items can touch in the same copper layer.

    A via in this design is always a through via (the board is 2-layer), so it
    spans every copper layer and always shares one with the other item. LSET
    does not support `&` under SWIG, hence the layer-by-layer comparison.
    """
    if isinstance(b, pcbnew.PCB_VIA):
        a, b = b, a
    if isinstance(a, pcbnew.PCB_VIA):
        # through via: spans F.Cu down to B.Cu, so it meets any copper layer
        return pcbnew.IsCopperLayer(b.GetLayer())
    return a.GetLayer() == b.GetLayer()


def _seg_endpoints(t):
    s, e = t.GetStart(), t.GetEnd()
    return (s.x / 1e6, s.y / 1e6), (e.x / 1e6, e.y / 1e6)


def _segments_touch(a, b):
    """True if either endpoint of `a` lies on `b` (T-junction or overlap)."""
    for p in _probes(a):
        if _point_on_segment(p, b):
            return True
    return False


def _width(item):
    """Item width in mm. PCB_VIA::GetWidth needs a layer, which SWIG enforces."""
    if isinstance(item, pcbnew.PCB_VIA):
        return item.GetWidth(item.TopLayer()) / 1e6
    return item.GetWidth() / 1e6


def _point_on_segment(p, t):
    (x1, y1), (x2, y2) = _seg_endpoints(t)
    if isinstance(t, pcbnew.PCB_VIA):
        cx, cy = p
        return math.hypot(cx - x1, cy - y1) <= _width(t) / 2
    # A little slack: KiCad rounds track ends to 1nm and routes meet at angles
    # that are not always exactly collinear.
    tol = max(_width(t) / 2, 0.001)
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - x1, p[1] - y1) <= tol
    t0 = ((p[0] - x1) * dx + (p[1] - y1) * dy) / (dx * dx + dy * dy)
    if t0 < 0 or t0 > 1:
        return False
    px, py = x1 + t0 * dx, y1 + t0 * dy
    return math.hypot(p[0] - px, p[1] - py) <= tol


def _pad_touches_track(pad, track):
    box = pad.GetBoundingBox()
    (x1, y1), (x2, y2) = _seg_endpoints(track)
    cx, cy = box.GetCenter().x / 1e6, box.GetCenter().y / 1e6
    half_w = box.GetWidth() / 2e6
    half_h = box.GetHeight() / 2e6
    # Sample along the track; a pad is at most 5.1mm across, so 0.25mm steps
    # cannot step over one.
    steps = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.25) + 1)
    for k in range(steps + 1):
        t = k / steps
        if abs(x1 + t * (x2 - x1) - cx) <= half_w and abs(y1 + t * (y2 - y1) - cy) <= half_h:
            return True
    return False


def _gap(ga, gb):
    best = None
    for a in ga:
        for b in gb:
            for pa in _probes(a) or []:
                for pb in _probes(b) or []:
                    d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                    if best is None or d < best:
                        best = d
    return best


if __name__ == "__main__":
    sys.exit(main())
