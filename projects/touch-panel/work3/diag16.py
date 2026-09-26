"""Name the copper that stops the ROW15 search 1.00mm short.

Both headers exhausted the whole grid and converged on the same closest cell
(0, 111, 1043), 1.00mm from any legal ROW15 goal cell.  Whatever sits between
them is a wall, and the only useful thing to do is say what it is made of.
"""
import sys, os, math, collections
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

edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

allc = list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                  for p in fp.Pads()]

name = "ROW15"
mine = [it for it in allc if it.GetNetname() == name]
obst = [it for it in allc if it.GetNetname() != name]

g = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
g.build(obst)
gol = [gc for gc in replan.cells_of(g, mine, LAYERS)
       if g.OK[gc[0]][gc[2], gc[1]]]

X, Y = g.xy(111, 1043)
print("closest cell (0,111,1043) -> (%.3f, %.3f) on F.Cu" % (X, Y))
print("grid origin %s  step %.3f" % (g.xy(0, 0), step))

# nearest legal goal cells
best = sorted(((math.hypot(g.xy(i, j)[0]-X, g.xy(i, j)[1]-Y), (l, i, j))
               for l, i, j in gol), key=lambda t: t[0])[:5]
for d, c in best:
    print("  goal cell %s at %s   %.3fmm away" % (c, g.xy(c[1], c[2]), d))

def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx-ax, by-ay
    L2 = dx*dx + dy*dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy)/L2))
    return math.hypot(px-(ax+t*dx), py-(ay+t*dy))

print("\ncopper within 1.5mm of that cell (the wall), by net:")
hits = collections.Counter()
for it in allc:
    if isinstance(it, pcbnew.PCB_TRACK) and not isinstance(it, pcbnew.PCB_VIA):
        s, e = it.GetStart(), it.GetEnd()
        d = seg_dist(X, Y, s.x/S, s.y/S, e.x/S, e.y/S) - it.GetWidth()/S/2
    elif isinstance(it, pcbnew.PCB_VIA):
        c = it.GetPosition()
        d = math.hypot(X-c.x/S, Y-c.y/S) - it.GetWidth()/S/2
    else:
        c = it.GetPosition()
        sz = it.GetSize()
        d = math.hypot(X-c.x/S, Y-c.y/S) - max(sz.x, sz.y)/S/2
    if d < 1.5:
        hits[it.GetNetname() or "<none>"] += 1
        if hits[it.GetNetname() or "<none>"] <= 3:
            if isinstance(it, pcbnew.PCB_TRACK):
                s, e = it.GetStart(), it.GetEnd()
                print("  %-8s %-4s (%.3f,%.3f)-(%.3f,%.3f) w=%.2f  gap %.3fmm" % (
                    it.GetNetname(), "F.Cu" if it.IsOnLayer(pcbnew.F_Cu) else "B.Cu",
                    s.x/S, s.y/S, e.x/S, e.y/S, it.GetWidth()/S, d))
            else:
                c = it.GetPosition()
                print("  %-8s PAD  %s @(%.3f,%.3f)  gap %.3fmm" % (
                    it.GetNetname(), it.GetParent().GetReference(),
                    c.x/S, c.y/S, d))
print("\n  total: %s" % dict(hits.most_common(12)))

# How wide is the free window in x on each layer, at several heights?  This is
# the number that matters: a comb of verticals is passable only where at least
# one cell survives between neighbours.
print("\nfree-cell runs in x, y 118 .. 236 (left gutter x 99 .. 104):")
print("   y      F.Cu free windows                                   B.Cu")
for j in range(1180, 2361, 40):
    y = g.xy(0, j)[1]
    row = []
    for l in (0, 1):
        runs, cur = [], 0
        for i in range(960, 1011):          # x 95.95 .. 101.05
            if g.OK[l][j, i]:
                cur += 1
            else:
                if cur:
                    runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        row.append(runs)
    print("  %.1f   %-46s %s" % (y, row[0], row[1]))
