"""Sound model M: the target net's own copper is *removed from the obstacle set*.

The previous version patched legality after the grid was built --
``OK | ((own_net == name) & (D < keep))`` -- and ``D``/``OWN`` only ever hold the
*distance to the nearest* item.  So whenever the nearest thing happened to be the
net's own trunk, the cell was opened without ever consulting the second-nearest,
which is another net's copper.  Measured consequence on the widened board:
ROW5 grazed GND at 0.0707mm and cut CSEL4 dead on B.Cu -- 12 violations.

Removing the items instead costs a second grid build and makes the exemption
unnecessary, so ``OK``/``VOK`` stay exactly as the grid computed them.
"""
import sys, os, types
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W, VIA_DIA, VIA_DRILL = 0.2, 0.6, 0.3
layers = [pcbnew.F_Cu, pcbnew.B_Cu]
OUT = '_v3.kicad_pcb'

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
E.widen(board)

TWO = {1: "ROW3", 20: "ROW5"}
j1a = E.place(board, "J1A", E.HDR_LIB, E.HDR_FP, E.LEFT_X, E.LEFT_Y, TWO)
print("placed J1A @(%.2f,%.2f)" % (E.LEFT_X, E.LEFT_Y), flush=True)
for p in j1a.Pads():
    if p.GetNetname():
        c = p.GetPosition()
        print("   pin %s -> %-5s @(%.2f,%.2f)" % (p.GetNumber(), p.GetNetname(),
                                                   c.x/S, c.y/S))

step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety          # 0.34
pad_keep = clearance + 0.3 + safety            # 0.54
egk = edge_clear + clearance + safety          # 0.64
vek = egk + 0.3                                # 0.94

def layer_runs(path):
    runs = [[path[0]]]
    for c in path[1:]:
        if c[0] != runs[-1][-1][0]:
            runs.append([c])
        else:
            runs[-1].append(c)
    return runs

def simplify_runs(runs):
    """Splice out layer excursions that would leave a dangling via."""
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
    nv = 0
    for k in range(1, len(runs)):
        lay, i, j = runs[k][0]
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

ALL = list(board.GetTracks()) + [p for fp in board.GetFootprints() for p in fp.Pads()]
j1a_pads = {p.m_Uuid.AsString() for p in j1a.Pads()}
print("board copper: %d item(s)" % len(ALL), flush=True)

total_t = total_v = 0
for name in ("ROW3", "ROW5"):
    # ---- model M, soundly: the target net's copper is simply not an obstacle
    items = [it for it in ALL if it.GetNetname() != name]
    grid = E.NGrid(board, step, keep, egk, pad_keep, vek, layers)
    grid.build(items)
    # J1A's own pads carry the net too, and the source pad's cells would make the
    # start a goal -- A* then returns a zero-length path.  They are the origin of
    # the route, not its destination.
    tgt = [it for it in ALL if it.GetNetname() == name
           and it.m_Uuid.AsString() not in j1a_pads]
    ys = []
    for it in tgt:
        bb = it.GetBoundingBox()
        ys += [bb.GetTop()/S, bb.GetBottom()/S]
    anchor = sorted(ys)[len(ys)//2]
    print("\n=== %s ===  %d obstacle(s), %d own item(s), anchor y=%.2f"
          % (name, len(items), len(tgt), anchor), flush=True)

    goals = {gc for gc in replan.cells_of(grid, tgt, layers)
             if grid.OK[gc[0]][gc[2], gc[1]]}
    print("  goals: %d legal cell(s)" % len(goals), flush=True)

    order = sorted(range(1, 21),
                   key=lambda n: abs(E.LEFT_Y - 0.0 + (n-1)*2.54 - anchor))
    best = None
    for pin in ([1, 20] if name else []) or order:
        src = j1a.FindPadByNumber(str(pin))
        if src.GetNetname() != name:
            continue
        c = src.GetPosition(); px, py = c.x/S, c.y/S
        ci, cj = grid.ij(px, py)
        start = []
        r = 4
        cand = [(l, ci+di, cj+dj) for l in layers
                for di in range(-r, r+1) for dj in range(-r, r+1)
                if 0 <= ci+di < grid.nx and 0 <= cj+dj < grid.ny]
        cand.sort(key=lambda c: (c[1]-ci)**2 + (c[2]-cj)**2)
        start = [c for c in cand if grid.OK[c[0]][c[2], c[1]]][:8]
        if not start:
            print("  pin %-2d @(%.2f,%.2f): no legal cell near pad" % (pin, px, py))
            continue
        path, cross, exp, closest = probe.astar(grid, start, goals, 25.0, conflict=False)
        if path is None:
            print("  pin %-2d @(%.2f,%.2f): NO PATH  expanded %d  closest %.2fmm"
                  % (pin, px, py, exp, closest[0]*step), flush=True)
            continue
        ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
                 for k in range(1, len(path))) * step
        runs = layer_runs(path); simp = simplify_runs(runs)
        print("  pin %-2d @(%.2f,%.2f): PATH %.1fmm  expanded %d  runs %d->%d vias %d"
              % (pin, px, py, ln, exp, len(runs), len(simp), len(simp)-1), flush=True)
        if best is None or ln < best[1]:
            best = (pin, ln, path, grid, simp)
        if pin in (1, 20):
            break
    if best is None:
        print("  >>> %s: UNROUTABLE under sound model" % name, flush=True)
        continue
    pin, ln, path, grid, simp = best
    nt, nv = emit(board, name, grid, path)
    print("  >>> %s on J1A pin %d: %.1fmm, %d track(s), %d via(s)"
          % (name, pin, ln, nt, nv), flush=True)
    total_t += nt; total_v += nv

print("\ntotal %d track(s), %d via(s)" % (total_t, total_v))
j1 = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1'][0]
for n in ("4", "6"):
    p = j1.FindPadByNumber(n)
    print("clearing net on J1 pad %s (was %s)" % (n, p.GetNetname()))
    p.SetNetCode(0)
pcbnew.SaveBoard(OUT, board)
print("saved to %s" % OUT)
