"""Minimal test: on the UNMODIFIED board, can J1.4 reach ROW3 and J1.6 reach ROW5?

Model M: the source pad and the target net's own copper are the only things that
are not obstacles.  No widening, no FPC removal, no schematic change.
"""
import sys, os, types
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S

j1 = None
for fp in board.GetFootprints():
    if fp.GetReference() == 'J1':
        j1 = fp
src = {"ROW3": j1.FindPadByNumber("4"), "ROW5": j1.FindPadByNumber("6")}
exempt = {p.m_Uuid.AsString() for p in src.values()}

items = list(board.GetTracks())
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.m_Uuid.AsString() not in exempt:
            items.append(p)
nameof = [it.GetNetname() for it in items]
nm = np.array(nameof, dtype=object)

for safety in (0.04, 0.02, 0.0):
    keep = 0.2 + 0.1 + safety
    pad_keep = 0.2 + 0.3 + safety
    egk = edge_clear + 0.2 + safety
    vek = egk + 0.3
    grid = E.NGrid(board, 0.1, keep, egk, pad_keep, vek, layers)
    grid.build(items)
    own_net = {}
    for lay in layers:
        o = grid.OWN[lay]
        own_net[lay] = np.where(o >= 0, nm[np.where(o >= 0, o, 0)], "")
    print("=== safety %.2f  keep %.3f  pad_keep %.3f ===" % (safety, keep, pad_keep), flush=True)
    for name in ("ROW3", "ROW5"):
        p = src[name]
        for target_pad_only in (False,):
            OK = {lay: grid.OK[lay] | ((own_net[lay] == name) & (grid.D[lay] < keep))
                  for lay in layers}
            VOK = grid.VOK | (np.logical_or.reduce([own_net[l] == name for l in layers])
                              & np.logical_and.reduce([grid.D[l] < pad_keep for l in layers]))
            g = types.SimpleNamespace()
            g.step, g.nx, g.ny, g.n = grid.step, grid.nx, grid.ny, grid.n
            g.layers, g.keep, g.D, g.OWN = layers, grid.keep, grid.D, grid.OWN
            g.OK, g.VOK, g.xy, g.ij, g.EG = OK, VOK, grid.xy, grid.ij, grid.EG
            c = p.GetPosition()
            ci, cj = grid.ij(c.x / S, c.y / S)
            start = [(l, ci, cj) for l in layers if OK[l][cj, ci]]
            tgt = [it for it in items if it.GetNetname() == name]
            goals = {gc for gc in replan.cells_of(grid, tgt, layers)
                     if OK[gc[0]][gc[2], gc[1]]}
            tag = "pad-only" if target_pad_only else "full-net"
            if not start or not goals:
                print("  %-5s %-9s start=%d goals=%d  --  no legal seed/goal"
                      % (name, tag, len(start), len(goals)), flush=True)
                continue
            path, cross, exp, closest = probe.astar(g, start, goals, 25.0, conflict=False)
            if path is None:
                print("  %-5s %-9s NO PATH  goals %5d  expanded %8d  closest %.2fmm"
                      % (name, tag, len(goals), exp, closest[0] * 0.1), flush=True)
            else:
                ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2) ** 0.5
                         for k in range(1, len(path))) * 0.1
                nv = sum(1 for k in range(1, len(path)) if path[k][0] != path[k-1][0])
                print("  %-5s %-9s PATH %.1fmm  expanded %8d  vias %d"
                      % (name, tag, ln, exp, nv), flush=True)
