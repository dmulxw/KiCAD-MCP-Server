"""Can J1 pad 4 (ROW3) / pad 6 (ROW5) still reach their own net's copper?

Sound model M: the target net's own copper is removed from the obstacle list
entirely (never the post-hoc D<keep patch).  Start = the J1 pad centre,
goal = a legal cell of that net's copper.  Board is used as-is (already widened
and already carrying J1A/J1B) -- no widen(), no place().
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

step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + 0.1 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

for pinnum, netname in (("4", "ROW3"), ("6", "ROW5")):
    src = j1.FindPadByNumber(pinnum)
    # every item that is NOT on the target net, minus the source pad itself
    items = []
    for t in board.GetTracks():
        if t.GetNetname() != netname:
            items.append(t)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != netname:
                items.append(p)
    grid = E.NGrid(board, step, keep, egk, pad_keep, vek, layers)
    grid.build(items)

    c = src.GetPosition()
    ci, cj = grid.ij(c.x / S, c.y / S)
    start = [(l, ci, cj) for l in layers if grid.OK[l][cj, ci]]
    print("=== J1.%s (%s) @ (%.3f, %.3f)  start cells %d  items %d"
          % (pinnum, netname, c.x/S, c.y/S, len(start), len(items)), flush=True)
    if not start:
        print("    pad centre itself is not legal"); continue

    suid = src.m_Uuid.AsString()
    tgt = [it for it in board.GetTracks() if it.GetNetname() == netname]
    tgt += [p for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == netname and p.m_Uuid.AsString() != suid]
    goals = {gc for gc in replan.cells_of(grid, tgt, layers)
             if grid.OK[gc[0]][gc[2], gc[1]]}
    print("    goal cells %d" % len(goals), flush=True)
    path, cross, exp, closest = probe.astar(grid, start, goals, 25.0,
                                            conflict=False)
    if path is None:
        print("    NO PATH   expanded %d   closest %s" % (exp, closest), flush=True)
    else:
        ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
                 for k in range(1, len(path))) * step
        print("    PATH %.1fmm  expanded %d  vias %d" % (ln, exp, sum(
            1 for k in range(1, len(path)) if path[k][0] != path[k-1][0])), flush=True)
