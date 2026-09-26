"""Two tracks, sound model M, sequential, with the pin chosen by measurement.

Three things were wrong before:
  * legality was patched after the grid build using a nearest-item-only
    distance, which opened cells that were clear of the net's own copper but
    not of someone else's (7 clearance + 4 shorts);
  * the obstacle list was snapshotted once, so the second net could not see the
    first net's freshly emitted copper -- the two long loops crossed 26 times;
  * pin 1 sits *above* the GND wall (y 126.61-132.50), so ROW3 could not enter
    its own trunk from there and had to loop 96.9mm over the top of the board.
    The wall's lower end is open: from pin 10 the same trunk is 22.7mm away.
"""
import sys, os, types
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W, VIA_DIA, VIA_DRILL = 0.2, 0.6, 0.3
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
OUT = '_v4.kicad_pcb'

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
E.widen(board)
j1a = E.place(board, "J1A", E.HDR_LIB, E.HDR_FP, E.LEFT_X, E.LEFT_Y, None)
print("placed J1A @(%.2f,%.2f), nets unassigned for now" % (E.LEFT_X, E.LEFT_Y), flush=True)
J1A_PADS = {p.m_Uuid.AsString() for p in j1a.Pads()}

step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

def layer_runs(path):
    runs = [[path[0]]]
    for c in path[1:]:
        runs[-1].append(c) if c[0] == runs[-1][-1][0] else runs.append([c])
    return runs

def simplify_runs(runs):
    changed = True
    while changed and len(runs) >= 3:
        changed = False
        for k in range(1, len(runs) - 1):
            a, b, c = runs[k-1], runs[k], runs[k+1]
            if a[0][0] != c[0][0]:
                continue
            d = (((a[-1][1]-c[0][1])**2 + (a[-1][2]-c[0][2])**2) ** 0.5) * step
            if d >= VIA_DIA:
                continue
            runs = runs[:k-1] + [a + c] + runs[k+2:]
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
    nv = nt = 0
    for k in range(1, len(runs)):
        lay, i, j = runs[k][0]
        x, y = grid.xy(i, j)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(round(x*S)), int(round(y*S))))
        v.SetWidth(int(VIA_DIA*S)); v.SetDrill(int(VIA_DRILL*S))
        v.SetNet(net); board.Add(v); nv += 1
    for run in runs:
        for lay, i0, j0, i1, j1 in merge_run(run):
            if i0 == i1 and j0 == j1:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(round(grid.xy(i0, j0)[0]*S)), int(round(grid.xy(i0, j0)[1]*S))))
            t.SetEnd(pcbnew.VECTOR2I(int(round(grid.xy(i1, j1)[0]*S)), int(round(grid.xy(i1, j1)[1]*S))))
            t.SetWidth(int(TRACK_W*S)); t.SetLayer(lay); t.SetNet(net)
            board.Add(t); nt += 1
    return nt, nv

def grid_for(name, allc):
    items = [it for it in allc if it.GetNetname() != name]
    g = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
    g.build(items)
    return g, items

def start_cells(grid, pad):
    c = pad.GetPosition(); ci, cj = grid.ij(c.x/S, c.y/S)
    cand = []
    for l in LAYERS:
        for di in range(-5, 6):
            for dj in range(-5, 6):
                i, j = ci+di, cj+dj
                if 0 <= i < grid.nx and 0 <= j < grid.ny and grid.OK[l][j, i]:
                    cand.append((di*di+dj*dj, (l, i, j)))
    cand.sort()
    return [c for _, c in cand[:8]]

def astar(g):
    pass

# ============================ phase 1: measure every pin ====================
print("\n### phase 1 -- measured hop from each J1A pin to each net's own copper")
best = {}
for name in ("ROW3", "ROW5"):
    # J1A pads are excluded so any pin can serve as the start; at 2.54mm pitch
    # with 1.7mm pads the 0.84mm gap leaves 0.42mm per side, over the 0.34mm keep,
    # so this optimism cannot manufacture a route that does not exist.
    items = [it for it in list(board.GetTracks())
             + [p for fp in board.GetFootprints() for p in fp.Pads()]
             if it.GetNetname() != name and it.m_Uuid.AsString() not in J1A_PADS]
    grid = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
    grid.build(items)
    tgt = [it for it in list(board.GetTracks())
           + [p for fp in board.GetFootprints() for p in fp.Pads()]
           if it.GetNetname() == name and it.m_Uuid.AsString() not in J1A_PADS]
    goals = {gc for gc in replan.cells_of(grid, tgt, LAYERS)
             if grid.OK[gc[0]][gc[2], gc[1]]}
    print("\n%s: %d obstacle(s), %d goal cell(s)" % (name, len(items), len(goals)), flush=True)
    res = []
    for n in range(1, 21):
        pad = j1a.FindPadByNumber(str(n))
        st = start_cells(grid, pad)
        if not st:
            continue
        path, cross, exp, closest = probe.astar(grid, st, goals, 25.0, conflict=False)
        c = pad.GetPosition()
        if path is None:
            res.append((n, c.y/S, None, exp, closest[0]*step))
            continue
        ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
                 for k in range(1, len(path))) * step
        res.append((n, c.y/S, ln, exp, 0.0))
    for n, y, ln, exp, cl in res:
        print("   pin %-2d y=%7.2f  %s" % (n, y,
              ("%6.1f mm  runs %d" % (ln, len(layer_runs(
                  probe.astar(grid, start_cells(grid, j1a.FindPadByNumber(str(n))),
                              goals, 25.0, conflict=False)[0])))) if ln is not None
              else "NO PATH  closest %.2fmm" % cl), flush=True)
    ok = [(ln, n) for n, y, ln, exp, cl in res if ln is not None]
    ok.sort()
    best[name] = ok[0][1]
    print("   --> shortest: pin %d (%.1f mm);  next: %s"
          % (best[name], ok[0][0], ", ".join("pin%d %.1f" % (n, l) for l, n in ok[1:4])), flush=True)
print("\nchosen: %s" % best)
