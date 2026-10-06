"""Who seals J1 pad 4 / pad 6 in?  Flood, then name the frontier.

_probe_j1reach.py answered "no path" -- but it built the grid at
keep = clearance + w/2 + safety = 0.34, while the board itself was emitted at
clearance 0.2.  A no-path at 0.34 is sufficient to prove a path does not exist
at 0.34; it proves nothing at 0.2.  So run both, and when the flood is bounded,
report the owners of the cells just outside it -- the nets that are the wall.
A wall of GND is recoverable (it can be re-routed, as final.py did west of the
trunks); a wall of neighbouring ROW/CSEL copper is a planning problem.

    python _probe_j1wall.py
"""
import sys, os
from collections import Counter, deque
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
STEP = 0.1

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
j1 = next(fp for fp in board.GetFootprints() if fp.GetReference() == 'J1')


def flood(grid, start):
    """Bounded BFS over legal cells; returns reachable set."""
    seen = set(start)
    q = deque(start)
    while q:
        l, i, j = q.popleft()
        for nb in ((l, i+1, j), (l, i-1, j), (l, i, j+1), (l, i, j-1)):
            if nb[0] == l and (nb[1] < 0 or nb[2] < 0
                               or nb[1] >= grid.nx or nb[2] >= grid.ny):
                continue
            if nb in seen or not grid.OK[nb[0]][nb[2], nb[1]]:
                continue
            seen.add(nb)
            q.append(nb)
        for l2 in LAYERS:                       # layer change == a via
            nb = (l2, i, j)
            if nb in seen or not grid.OK[l2][j, i]:
                continue
            seen.add(nb)
            q.append(nb)
    return seen


for pinnum, netname, safety in (("4", "ROW3", 0.04), ("4", "ROW3", 0.0),
                                ("6", "ROW5", 0.04), ("6", "ROW5", 0.0)):
    src = j1.FindPadByNumber(pinnum)
    keep = 0.2 + 0.1 + safety                   # clearance + w/2 + safety
    pad_keep = 0.2 + 0.3 + safety
    egk = edge_clear + 0.2 + safety
    vek = egk + 0.3

    items = [t for t in board.GetTracks() if t.GetNetname() != netname]
    items += [p for fp in board.GetFootprints() for p in fp.Pads()
              if p.GetNetname() != netname]
    names = [it.GetNetname() for it in items]

    grid = E.NGrid(board, STEP, keep, egk, pad_keep, vek, LAYERS)
    grid.build(items)

    c = src.GetPosition()
    ci, cj = grid.ij(c.x / S, c.y / S)
    start = [(l, ci, cj) for l in LAYERS if grid.OK[l][cj, ci]]
    if not start:
        print("J1.%s keep=%.2f: pad centre illegal" % (pinnum, keep), flush=True)
        continue

    reach = flood(grid, start)
    xs = [grid.x0 + i * STEP for _, i, _ in reach]
    ys = [grid.y0 + j * STEP for _, _, j in reach]

    # who owns the ring of illegal cells immediately outside the reachable set
    wall = Counter()
    for l, i, j in reach:
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            i2, j2 = i + di, j + dj
            if not (0 <= i2 < grid.nx and 0 <= j2 < grid.ny):
                continue
            if (l, i2, j2) in reach:
                continue
            o = grid.OWN[l][j2, i2]
            if o >= 0:
                wall[names[o]] += 1

    print("J1.%s (%s) keep=%.2f  reach %d cells  x %.2f..%.2f  y %.2f..%.2f"
          % (pinnum, netname, keep, len(reach), min(xs), max(xs),
             min(ys), max(ys)), flush=True)
    print("     wall: %s" % ", ".join("%s x%d" % (n, c)
                                       for n, c in wall.most_common(8)), flush=True)
