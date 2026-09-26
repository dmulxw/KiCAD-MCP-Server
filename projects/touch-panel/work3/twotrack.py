"""Minimal completion: bring ROW3 and ROW5 out through the new left header.

Only two nets are routed.  The other 38 keep their existing J1 fan-out untouched,
so none of the 40-net rework -- and none of its congestion failures -- is in play.
"""
import sys, os, types, shutil
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W, VIA_DIA, VIA_DRILL = 0.2, 0.6, 0.3
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
OUT = '_v2.kicad_pcb'

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
print("outline before: x %.3f..%.3f  y %.3f..%.3f" % (
    board.GetBoardEdgesBoundingBox().GetLeft()/S, board.GetBoardEdgesBoundingBox().GetRight()/S,
    board.GetBoardEdgesBoundingBox().GetTop()/S, board.GetBoardEdgesBoundingBox().GetBottom()/S))
E.widen(board)
bb = board.GetBoardEdgesBoundingBox()
print("outline after : x %.3f..%.3f  y %.3f..%.3f" % (
    bb.GetLeft()/S, bb.GetRight()/S, bb.GetTop()/S, bb.GetBottom()/S))

TWO = {1: "ROW3", 20: "ROW5"}
j1a = E.place(board, "J1A", E.HDR_LIB, E.HDR_FP, E.LEFT_X, E.LEFT_Y, TWO)
print("placed J1A @(%.2f,%.2f)  nets: %s" % (
    E.LEFT_X, E.LEFT_Y,
    ", ".join("%s->%s" % (p.GetNumber(), p.GetNetname()) for p in j1a.Pads()
              if p.GetNetname())))

step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety          # 0.34
pad_keep = clearance + 0.3 + safety            # 0.54
egk = edge_clear + clearance + safety          # 0.64
vek = egk + 0.3                                # 0.94

# ---------------------------------------------------------------- emitter
def layer_runs(path):
    runs = [[path[0]]]
    for c in path[1:]:
        if c[0] != runs[-1][-1][0]:
            runs.append([c])
        else:
            runs[-1].append(c)
    return runs

def simplify_runs(runs):
    """Drop pointless layer excursions that would leave a dangling via.

    A run that lands back on the layer it came from, with both transitions
    inside one via diameter, is a detour the emitter cannot represent: the CSS
    dedup used to *silently skip* the second via and still emit both layer's
    tracks, which is exactly a dangling end.  Splicing the excursion out keeps
    the path and removes the impossibility.
    """
    changed = True
    while changed and len(runs) >= 3:
        changed = False
        for k in range(1, len(runs) - 1):
            a, b, c = runs[k-1], runs[k], runs[k+1]
            if a[0][0] != c[0][0]:
                continue
            ax, ay = a[-1][1], a[-1][2]
            bx, by = c[0][1], c[0][2]
            if ((ax-bx)**2 + (ay-by)**2) ** 0.5 * step >= VIA_DIA:
                continue
            runs = runs[:k] + [[c[0]] + a[-1:] ] if False else runs[:k] + [ ]
            # splice: a stays, c follows on the same layer
            newk = a + c
            runs = runs[:k-1] + [newk] + runs[k+2:]
            changed = True
            break
    return runs

def merge_run(run):
    if len(run) < 2:
        return []
    segs, start, prev = [], run[0], None
    for k in range(1, len(run)):
        d = (run[k][1]-run[k-1][1], run[k][2]-run[k-1][2])
        if prev is not None and d != prev:
            segs.append((run[0][0], start[1], start[2], run[k-1][1], run[k-1][2]))
            start = run[k-1]
        prev = d
    segs.append((run[0][0], start[1], start[2], run[-1][1], run[-1][2]))
    return segs

def emit(board, name, grid, path):
    runs = simplify_runs(layer_runs(path))
    net = board.FindNet(name)
    if net is None:
        raise SystemExit("no net %s" % name)
    vias = [runs[k][0] for k in range(1, len(runs))]
    nv = 0
    for lay, i, j in vias:
        x, y = grid.xy(i, j)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(round(x*S)), int(round(y*S))))
        v.SetWidth(int(VIA_DIA*S)); v.SetDrill(int(VIA_DRILL*S))
        v.SetNet(net); board.Add(v); nv += 1
    nt = 0
    for run in runs:
        for lay, i0, j0, i1, j1 in merge_run(run):
            if i0 == i1 and j0 == j1:
                continue
            x0, y0 = grid.xy(i0, j0); x1, y1 = grid.xy(i1, j1)
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(round(x0*S)), int(round(y0*S))))
            t.SetEnd(pcbnew.VECTOR2I(int(round(x1*S)), int(round(y1*S))))
            t.SetWidth(int(TRACK_W*S)); t.SetLayer(lay); t.SetNet(net)
            board.Add(t); nt += 1
    return nt, nv

# ---------------------------------------------------------------- route
total_t = total_v = 0
for pin, name in TWO.items():
    src = j1a.FindPadByNumber(str(pin))
    items = []
    for t in board.GetTracks():
        items.append(t)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.m_Uuid.AsString() != src.m_Uuid.AsString():
                items.append(p)
    nm = np.array([it.GetNetname() for it in items], dtype=object)
    grid = E.NGrid(board, step, keep, egk, pad_keep, vek, layers)
    grid.build(items)
    own_net = {}
    for lay in layers:
        o = grid.OWN[lay]
        own_net[lay] = np.where(o >= 0, nm[np.where(o >= 0, o, 0)], "")
    OK = {lay: grid.OK[lay] | ((own_net[lay] == name) & (grid.D[lay] < keep))
          for lay in layers}
    VOK = grid.VOK | (np.logical_or.reduce([own_net[l] == name for l in layers])
                      & np.logical_and.reduce([grid.D[l] < pad_keep for l in layers]))
    g = types.SimpleNamespace()
    g.step, g.nx, g.ny, g.n = grid.step, grid.nx, grid.ny, grid.n
    g.layers, g.keep, g.D, g.OWN = layers, grid.keep, grid.D, grid.OWN
    g.OK, g.VOK, g.xy, g.ij, g.EG = OK, VOK, grid.xy, grid.ij, grid.EG
    c = src.GetPosition(); ci, cj = grid.ij(c.x/S, c.y/S)
    start = [(l, ci, cj) for l in layers if OK[l][cj, ci]]
    tgt = [it for it in items if it.GetNetname() == name]
    goals = {gc for gc in replan.cells_of(grid, tgt, layers) if OK[gc[0]][gc[2], gc[1]]}
    print("\n%s from J1A pin %d @ (%.3f,%.3f):  start %d cell(s), goals %d"
          % (name, pin, c.x/S, c.y/S, len(start), len(goals)), flush=True)
    if not start or not goals:
        print("  no start/goal -- skipping", flush=True); continue
    path, cross, exp, closest = probe.astar(g, start, goals, 25.0, conflict=False)
    if path is None:
        print("  NO PATH  expanded %d  closest %.2fmm" % (exp, closest[0]*step), flush=True)
        continue
    ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
             for k in range(1, len(path))) * step
    runs = layer_runs(path); simp = simplify_runs(runs)
    print("  PATH %.1fmm  expanded %d  runs %d -> %d after simplify  (excursions removed: %d)"
          % (ln, exp, len(runs), len(simp), len(runs)-len(simp)), flush=True)
    nt, nv = emit(board, name, grid, path)
    print("  emitted %d track(s), %d via(s)" % (nt, nv), flush=True)
    total_t += nt; total_v += nv

print("\ntotal %d track(s), %d via(s)" % (total_t, total_v))

# ---- retire the two J1 pads that the header now supersedes
j1 = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1'][0]
for n in ("4", "6"):
    p = j1.FindPadByNumber(n)
    print("clearing net on J1 pad %s (was %s)" % (n, p.GetNetname()))
    p.SetNetCode(0)

pcbnew.SaveBoard(OUT, board)
print("saved to %s" % OUT)
