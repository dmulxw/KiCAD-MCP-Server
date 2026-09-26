"""How many of the pocket's walls must open before J1.4 can reach ROW3?

'Opening' an item = clearing its OWN cells in the legality map, without rebuilding
the grid.  Cheap, and exactly equivalent to lifting that item.
"""
import sys, os, collections
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
j1 = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1'][0]
src = {"ROW3": j1.FindPadByNumber("4"), "ROW5": j1.FindPadByNumber("6")}
exempt = {p.m_Uuid.AsString() for p in src.values()}
items = list(board.GetTracks())
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.m_Uuid.AsString() not in exempt:
            items.append(p)
nm = np.array([it.GetNetname() for it in items], dtype=object)
li = {l: k for k, l in enumerate(layers)}
NB = ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))

safety = 0.0
keep = 0.2 + 0.1 + safety; pad_keep = 0.2 + 0.3 + safety
egk = edge_clear + 0.2 + safety; vek = egk + 0.3
grid = E.NGrid(board, 0.1, keep, egk, pad_keep, vek, layers)
grid.build(items)
own_net = {}
for lay in layers:
    o = grid.OWN[lay]
    own_net[lay] = np.where(o >= 0, nm[np.where(o >= 0, o, 0)], "")
print("grid ready", flush=True)

for name in ("ROW3", "ROW5"):
    baseOK = {lay: grid.OK[lay] | ((own_net[lay] == name) & (grid.D[lay] < keep))
              for lay in layers}
    VOK = grid.VOK | (np.logical_or.reduce([own_net[l] == name for l in layers])
                      & np.logical_and.reduce([grid.D[l] < pad_keep for l in layers]))
    gmask = {lay: np.zeros((grid.ny, grid.nx), bool) for lay in layers}
    for gc in replan.cells_of(grid, [it for it in items if it.GetNetname() == name], layers):
        if baseOK[gc[0]][gc[2], gc[1]]:
            gmask[gc[0]][gc[2], gc[1]] = True
    H = {lay: probe.octile_dt(gmask[lay], grid.step) for lay in layers}
    p = src[name]; c = p.GetPosition(); ci, cj = grid.ij(c.x/S, c.y/S)

    def flood(OK):
        seen = set(); q = collections.deque()
        for lay in layers:
            if OK[lay][cj, ci]:
                seen.add((li[lay], ci, cj)); q.append((li[lay], ci, cj))
        wall = collections.Counter()
        best = 1e18
        while q:
            l, i, j = q.popleft(); lay = layers[l]
            h = H[lay][j, i]
            if h < best: best = h
            for di, dj in NB:
                ni, nj = i+di, j+dj
                if not (0 <= ni < grid.nx and 0 <= nj < grid.ny): continue
                if di and dj and not (OK[lay][j, ni] and OK[lay][nj, i]):
                    for (qi, qj) in ((ni, j), (i, nj)):
                        o = grid.OWN[lay][qj, qi]
                        if o >= 0: wall[int(o)] += 1
                    continue
                if OK[lay][nj, ni]:
                    nk = (l, ni, nj)
                    if nk not in seen: seen.add(nk); q.append(nk)
                else:
                    o = grid.OWN[lay][nj, ni]
                    if o >= 0: wall[int(o)] += 1
            if VOK[j, i]:
                for ol in layers:
                    if ol == lay: continue
                    m = li[ol]
                    if OK[ol][j, i]:
                        nk = (m, i, j)
                        if nk not in seen: seen.add(nk); q.append(nk)
        return len(seen), best * 0.1, wall

    n0, d0, wall0 = flood(baseOK)
    print("=== %s : pad %s ===" % (name, p.GetNumber()))
    print("  K=0  pocket %7d cell(s)   nearest %s copper: %.2fmm" % (n0, name, d0), flush=True)
    order = [o for o, _ in wall0.most_common()]
    free = []
    for K in (1, 2, 3, 4, 5, 6, 8, 10, 12, 16):
        while len(free) < K:
            free.append(order[len(free)])
        OK = {lay: baseOK[lay].copy() for lay in layers}
        for o in free:
            for lay in layers:
                OK[lay][grid.OWN[lay] == o] = True
        n, d, _ = flood(OK)
        o_last = items[free[K-1]]
        print("  K=%-2d pocket %7d cell(s)   nearest %s copper: %7.2fmm   (+%-6s %s)"
              % (K, n, name, d, o_last.GetNetname(),
                 "trk" if isinstance(o_last, pcbnew.PCB_TRACK) else "pad"), flush=True)
    print(flush=True)
