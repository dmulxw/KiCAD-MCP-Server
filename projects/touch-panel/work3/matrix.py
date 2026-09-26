"""Which net can each header pin actually CONNECT to (model M, no interference).

One grid per header, built from the real board with all 39 other header pins
present; the source pin's own pad and the target net's own copper are the only
things that are not obstacles. The search starts on the source pad's centre and
must land on a cell of the target's copper, so "reachable" here means a track
that touches both ends -- not a halo graze.
"""
import sys, os, types, time
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
DISTINCT = (["ROW%d" % k for k in range(21)]
            + ["CSEL%d" % k for k in range(10)] + ["GND", "+3V3"])

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
E.widen(board)
hdr = {}
for r_, x, y in (("J1A", E.LEFT_X, E.LEFT_Y), ("J1B", E.RIGHT_X, E.RIGHT_Y)):
    hdr[r_] = E.place(board, r_, E.HDR_LIB, E.HDR_FP, x, y, E.ASSIGN[r_])

step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + 0.1 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

out = {}
for ref, pin in (("J1A", 10), ("J1B", 10)):
    src = hdr[ref].FindPadByNumber(pin)
    items = list(board.GetTracks())
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.m_Uuid.AsString() != src.m_Uuid.AsString():
                items.append(p)
    grid = E.NGrid(board, step, keep, egk, pad_keep, vek, layers)
    grid.build(items)
    nameof = []
    for it in items:
        try: nameof.append(it.GetNetname())
        except Exception: nameof.append("")
    nm = np.array(nameof, dtype=object)
    own_net = {}
    for lay in layers:
        o = grid.OWN[lay]
        own_net[lay] = np.where(o >= 0, nm[np.where(o >= 0, o, 0)], "")

    c = src.GetPosition()
    ci, cj = grid.ij(c.x / S, c.y / S)
    print("=== %s pin %d @ (%.2f, %.2f) ===" % (ref, pin, c.x / S, c.y / S), flush=True)
    got = {}
    for name in DISTINCT:
        OK = {lay: grid.OK[lay] | ((own_net[lay] == name) & (grid.D[lay] < keep))
              for lay in layers}
        VOK = grid.VOK | (np.logical_or.reduce([own_net[l] == name for l in layers])
                          & np.logical_and.reduce([grid.D[l] < pad_keep for l in layers]))
        g = types.SimpleNamespace()
        g.step, g.nx, g.ny, g.n = grid.step, grid.nx, grid.ny, grid.n
        g.layers, g.keep, g.D, g.OWN = layers, grid.keep, grid.D, grid.OWN
        g.OK, g.VOK, g.xy, g.ij, g.EG = OK, VOK, grid.xy, grid.ij, grid.EG
        start = [(lay, ci, cj) for lay in layers if OK[lay][cj, ci]]
        if not start:
            got[name] = None; continue
        tgt = [it for it in items if getattr(it, "GetNetname", lambda: "")() == name]
        goals = {gc for gc in replan.cells_of(grid, tgt, layers)
                 if OK[gc[0]][gc[2], gc[1]]}
        if not goals:
            got[name] = None
            print("    %-6s  no legal goal (%d sampled)" % (name, len(goals)), flush=True)
            continue
        path, cross, exp, closest = probe.astar(g, start, goals, 25.0, conflict=False)
        if path is None:
            got[name] = None
            print("    %-6s  NO PATH  goals %5d  expanded %7d" % (name, len(goals), exp), flush=True)
        else:
            ln = sum(((path[k][1] - path[k - 1][1]) ** 2
                      + (path[k][2] - path[k - 1][2]) ** 2) ** 0.5
                     for k in range(1, len(path))) * step
            got[name] = ln
            print("    %-6s  %7.1fmm  goals %5d  expanded %7d" % (name, ln, len(goals), exp), flush=True)
    out[ref] = got

L = {n for n in DISTINCT if out["J1A"].get(n) is not None}
R = {n for n in DISTINCT if out["J1B"].get(n) is not None}
print("\n=== model-M reachability (touching both ends) ===")
print("J1A: %2d/33  %s" % (len(L), " ".join(sorted(L))))
print("J1B: %2d/33  %s" % (len(R), " ".join(sorted(R))))
print("only-left : %s" % " ".join(sorted(L - R)))
print("only-right: %s" % " ".join(sorted(R - L)))
print("either    : %s" % " ".join(sorted(L & R)))
print("neither   : %s" % " ".join(sorted(set(DISTINCT) - L - R)))
DEM = {n: 1 for n in DISTINCT}; DEM["GND"] = 5; DEM["+3V3"] = 4
def dem(s): return sum(DEM[n] for n in s)
print("\ndemand  only-left %d  only-right %d  either %d  neither %d  (total %d)"
      % (dem(L - R), dem(R - L), dem(L & R), dem(set(DISTINCT) - L - R), dem(DISTINCT)))
print("left header needs 20 slots: %d exclusive + %d of the shared pool"
      % (dem(L - R), 20 - dem(L - R)))
print("right header needs 20 slots: %d exclusive + %d of the shared pool"
      % (dem(R - L), 20 - dem(R - L)))
import pickle; pickle.dump(out, open('_matrix.pkl', 'wb'))
