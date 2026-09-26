"""Escape capacity of every J1 signal pin.

For each J1 net in turn, ask: if that net's own copper were gone and a fresh
trace had to leave its pad, how far could it get? The grid blocks every other
net, so the answer is the size and reach of the free pocket around that pin.

A pin whose pocket stops at y~241 is sealed -- whatever net sits there cannot
be routed, which is exactly ROW3/ROW5's situation on pads 4 and 6. A pin whose
pocket reaches y<200 has a corridor north and can carry a row.

    python scan.py            # all J1 nets, ~40 grid builds
"""
import sys, time
from collections import deque

import numpy as np
import pcbnew

sys.path.insert(0, ".")
from probe import NGrid
from replan import Router, pad_cells

S = 1e6
BOARD = ("D:/source/repos/KiCAD-MCP-Server/projects/touch-panel/work3/"
         "replan/p1.kicad_pcb")
NB = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def pocket(board, r, name):
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    g = NGrid(board, 0.05, r.keep, r.edge_keep, r.pad_keep, r.via_edge_keep,
              layers)
    g.build(r.obstacles(name))
    src = next(p for p in r.j1.Pads() if p.GetNetname() == name)
    start = pad_cells(g, src, layers)
    seen = set(start)
    q = deque(start)
    while q:
        lay, i, j = q.popleft()
        for di, dj in NB:
            ni, nj = i + di, j + dj
            if not (0 <= ni < g.nx and 0 <= nj < g.ny):
                continue
            if not g.OK[lay][nj, ni]:
                continue
            k = (lay, ni, nj)
            if k not in seen:
                seen.add(k)
                q.append(k)
        if g.VOK[j, i]:
            for o in layers:
                if o != lay and (o, i, j) not in seen:
                    seen.add((o, i, j))
                    q.append((o, i, j))
    xs = np.array([g.xy(i, j)[0] for _, i, j in seen])
    ys = np.array([g.xy(i, j)[1] for _, i, j in seen])
    return len(seen), xs.min(), xs.max(), ys.min(), ys.max()


def main():
    board = pcbnew.LoadBoard(BOARD)
    r = Router(board, 0.05, 0.04, 0.2, [pcbnew.F_Cu, pcbnew.B_Cu],
               board.GetDesignSettings().m_CopperEdgeClearance / S)
    names = []
    for p in r.j1.Pads():
        n = p.GetNetname()
        if n and n not in names:
            names.append(n)
    print(f"{'net':<8} {'pad':>4} {'cells':>9} {'min_y':>8} {'max_y':>8} "
          f"{'x range':>17}  verdict")
    print("-" * 74)
    for n in names:
        pad = next(p for p in r.j1.Pads() if p.GetNetname() == n)
        t = time.time()
        c, x0, x1, y0, y1 = pocket(board, r, n)
        if y0 < 200:
            v = "OPEN (reaches north)"
        elif y0 < 239:
            v = "partial"
        else:
            v = "SEALED"
        print(f"{n:<8} {pad.GetNumber():>4} {c:>9} {y0:>8.2f} {y1:>8.2f} "
              f"{x0:>8.2f}..{x1:<8.2f}  {v}  [{time.time()-t:.0f}s]")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
