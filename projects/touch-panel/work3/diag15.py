"""ROW15 is 'unreachable from both' while ROW18, four rows away on the same
header, is 22.4mm.  In a periodic array that cannot be geometry.  Discriminate:

  A. no obstacles at all          -> is the goal cell itself bad?
  B. obstacles, own net exempted  -> the real question (reproduces bothsides.py)
  C. same as B, but report how close the search actually got
"""
import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W = 0.2
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

board = pcbnew.LoadBoard('_final.kicad_pcb')
GRAVE = []
j1b = E.place(board, "J1B", E.HDR_LIB, E.HDR_FP, E.RIGHT_X, E.RIGHT_Y, {})
j1a = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1A'][0]
j1a_pads = {p.m_Uuid.AsString() for p in j1a.Pads()}
j1b_pads = {p.m_Uuid.AsString() for p in j1b.Pads()}
hdr_pads = j1a_pads | j1b_pads

edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

def make_grid(items):
    g = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
    g.build(items)
    return g

def bbox(items):
    xs, ys = [], []
    for it in items:
        bb = it.GetBoundingBox()
        xs += [bb.GetLeft()/S, bb.GetRight()/S]
        ys += [bb.GetTop()/S, bb.GetBottom()/S]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None

allc = list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                  for p in fp.Pads()]

for name in ("ROW15", "ROW18", "CSEL0", "CSEL3"):
    mine = [it for it in allc if it.GetNetname() == name
            and it.m_Uuid.AsString() not in hdr_pads]
    print("\n=== %s ===" % name)
    print("  own copper : %d item(s) bbox %s" % (len(mine), bbox(mine)))
    trk = [it for it in mine if isinstance(it, pcbnew.PCB_TRACK)]
    print("  of which   : %d track(s), %d pad(s)"
          % (sum(1 for t in trk if not isinstance(t, pcbnew.PCB_VIA)),
             len(mine) - len(trk)))

    for tag, own, fp in (("J1A", j1a_pads, j1a), ("J1B", j1b_pads, j1b)):
        obst = [it for it in allc
                if it.GetNetname() != name and it.m_Uuid.AsString() not in own]
        for label, items in (("A. no obstacles", []), ("B. real", obst)):
            grid = make_grid(items)
            gol = [gc for gc in replan.cells_of(grid, mine, LAYERS)
                   if grid.OK[gc[0]][gc[2], gc[1]]]
            if not gol:
                print("  %s %-15s goals EMPTY" % (tag, label))
                continue
            st = list(dict.fromkeys(replan.cells_of(grid, list(fp.Pads()), LAYERS)))
            path, cross, exp, closest = probe.astar(grid, st, set(gol), 25.0,
                                                    conflict=False)
            if path is None:
                d, c = closest
                print("  %s %-15s NO PATH  goals %d  expanded %d  closest %.2fmm "
                      "at %s  start cells %d"
                      % (tag, label, len(gol), exp, d*step, c, len(st)), flush=True)
            else:
                ln = sum(((path[k][1]-path[k-1][1])**2
                          + (path[k][2]-path[k-1][2])**2)**0.5
                         for k in range(1, len(path))) * step
                print("  %s %-15s %.1fmm  goals %d  expanded %d"
                      % (tag, label, ln, len(gol), exp), flush=True)
