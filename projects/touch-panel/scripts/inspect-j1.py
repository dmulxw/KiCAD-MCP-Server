#!/usr/bin/env python3
"""Show J1's pads and the copper packed around them.

Seven of the 31 signal pads on J1 (a 0.5mm-pitch 40-pin ZIF) came out of the
last autoroute with no track attached at all, while the rest of each of those
nets is fully routed. That is a different failure from a stranded net: the
router built the tree and never reached the connector. This prints what is
physically in the way, so the fix is chosen from geometry rather than guessed.

    docker run --rm -v D:/source/repos/KiCAD-MCP-Server:/workspace \
        -w /workspace kicad-mcp:9.0 \
        /opt/kicad-mcp-venv/bin/python \
        projects/touch-panel/scripts/inspect-j1.py
"""

import math

import pcbnew

BOARD = "/workspace/projects/touch-panel/touch-panel.kicad_pcb"
NEARBY = 8.0  # mm around J1 to report copper from
REF = "J1"


def main():
    board = pcbnew.LoadBoard(BOARD)

    j1 = board.FindFootprintByReference(REF)
    if j1 is None:
        raise SystemExit(f"no {REF} on the board")

    centre = j1.GetPosition()
    cx, cy = centre.x / 1e6, centre.y / 1e6
    print(f"{REF} at ({cx:.3f}, {cy:.3f})")

    pads = sorted(j1.Pads(), key=lambda p: p.GetNumber())
    print(f"\n{len(pads)} pad(s):")
    for pad in pads:
        p = pad.GetPosition()
        px, py = p.x / 1e6, p.y / 1e6
        size = pad.GetSize()
        is_npth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
        net = pad.GetNetname() or "-"
        print(f"  {pad.GetNumber():>3} ({px:8.3f},{py:8.3f})"
              f" {size.x / 1e6:.2f}x{size.y / 1e6:.2f}"
              f" drill={pad.GetDrillSize().x / 1e6:.2f}"
              f" npth={int(is_npth)} net={net}")

    # Every copper item whose geometry comes within NEARBY of J1, so the
    # congestion around the connector is visible rather than inferred.
    print(f"\ncopper within {NEARBY}mm of {REF}:")
    rows = []
    for track in board.GetTracks():
        s, e = track.GetStart(), track.GetEnd()
        sx, sy, ex, ey = s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6
        d = _seg_point_distance((sx, sy), (ex, ey), (cx, cy))
        if d <= NEARBY:
            layer = board.GetLayerName(track.GetLayer())
            kind = "via" if isinstance(track, pcbnew.PCB_VIA) else "trk"
            rows.append((d, f"  {d:5.2f}mm {kind} {board.FindNet(track.GetNetCode()).GetNetname():<8}"
                            f" {layer:<5} ({sx:8.3f},{sy:8.3f})->({ex:8.3f},{ey:8.3f})"))
    for fp in board.GetFootprints():
        if fp.GetReference() == REF:
            continue
        for pad in fp.Pads():
            p = pad.GetPosition()
            px, py = p.x / 1e6, p.y / 1e6
            d = math.hypot(px - cx, py - cy)
            if d <= NEARBY:
                rows.append((d, f"  {d:5.2f}mm pad {fp.GetReference()}.{pad.GetNumber()}"
                                 f" ({px:8.3f},{py:8.3f}) net={pad.GetNetname() or '-'}"))
    for d, line in sorted(rows):
        print(line)


def _seg_point_distance(a, b, p):
    (x1, y1), (x2, y2) = a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - x1, p[1] - y1)
    t = ((p[0] - x1) * dx + (p[1] - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (x1 + t * dx), p[1] - (y1 + t * dy))


if __name__ == "__main__":
    main()
