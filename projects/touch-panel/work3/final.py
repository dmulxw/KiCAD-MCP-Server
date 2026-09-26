"""Final: clear the GND wall, feed ROW3/ROW5 sideways from the new header.

Measured on the widened board (work3/walltest.py):

    net    candidate pin         wall in place   wall removed
    ROW3   J1A pin 5  y=125.83      107.1 mm       6.1 mm
    ROW5   J1A pin 10 y=138.53      119.8 mm       6.2 mm

The wall is 30 GND segments running x~100.3-102.4, y 118-148 -- not the single
0.9mm piece it looked like, but one long link that seals the west end of BOTH
trunks.  Cutting it drops 207mm of detour to 12mm.

It is a link, not a spur: GND goes from 1 island to 7.  So the wall is removed
and GND is immediately re-routed around the two new corridors -- which is the
only honest form of taking the wall out.
"""
import sys, os, math
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W, VIA_DIA, VIA_DRILL = 0.2, 0.6, 0.3
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
OUT = '_final.kicad_pcb'
GRAVE = []                       # removed items must outlive their SWIG proxies

WIN = (100.30, 118.00, 102.40, 148.00)
PIN = {"ROW3": 5, "ROW5": 10}

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
E.widen(board)

step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

# ------------------------------------------------------------ 1. the wall
x0, y0, x1, y1 = WIN
wall = []
for it in board.GetTracks():
    if it.GetNetname() != 'GND':
        continue
    bb = it.GetBoundingBox()
    if (bb.GetLeft()/S >= x0 and bb.GetRight()/S <= x1
            and bb.GetTop()/S >= y0 and bb.GetBottom()/S <= y1):
        wall.append(it)
ys = []
for it in wall:
    bb = it.GetBoundingBox()
    ys += [bb.GetTop()/S, bb.GetBottom()/S]
print("1. removing %d GND segment(s); the wall runs y %.2f .. %.2f"
      % (len(wall), min(ys), max(ys)), flush=True)
for it in wall:
    board.Remove(it)
    GRAVE.append(it)

# ------------------------------------------------------------ 2. header
j1a = E.place(board, "J1A", E.HDR_LIB, E.HDR_FP, E.LEFT_X, E.LEFT_Y,
              {n: nm for nm, n in PIN.items()})
j1a_pads = {p.m_Uuid.AsString() for p in j1a.Pads()}
print("\n2. J1A @(%.2f,%.2f): %s" % (
    E.LEFT_X, E.LEFT_Y,
    ", ".join("pin %s -> %s" % (p.GetNumber(), p.GetNetname())
              for p in j1a.Pads() if p.GetNetname())), flush=True)

# ------------------------------------------------------------ emitter
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

def attach_pt(px, py, items):
    """Nearest point that lies *on the centreline* of some same-net copper.

    Grinding to the nearest copper is not enough.  A track endpoint that lands
    beside a parallel track -- inside its 0.2mm body but off its centreline by
    0.032mm -- is not a connection at all: KiCad's connectivity intersects
    centrelines, so two side-by-side verticals that overlap by a third of a
    width are still two separate islands.  That is the one remaining
    track_dangling.  Projecting onto the segment instead makes the centrelines
    meet, which is what actually joins them.
    """
    best = (1e18, None)
    for it in items:
        if isinstance(it, pcbnew.PCB_TRACK) and not isinstance(it, pcbnew.PCB_VIA):
            s, e = it.GetStart(), it.GetEnd()
            ax, ay, bx, by = s.x/S, s.y/S, e.x/S, e.y/S
            dx, dy = bx-ax, by-ay
            L2 = dx*dx + dy*dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy)/L2))
            q = (ax+t*dx, ay+t*dy)
            d = ((px-q[0])**2 + (py-q[1])**2) ** 0.5
            if d < best[0]:
                best = (d, (q[0], q[1], it.GetLayer()))
        else:
            c = it.GetPosition()
            q = (c.x/S, c.y/S)
            d = ((px-q[0])**2 + (py-q[1])**2) ** 0.5
            if d < best[0]:
                lay = ([l for l in LAYERS if it.IsOnLayer(l)] or [LAYERS[0]])[0]
                best = (d, (q[0], q[1], lay))
    return best[1] if best[1] else None


def emit(board, name, grid, path, pre=None, post=None):
    runs = simplify_runs(layer_runs(path))
    net = board.FindNet(name)
    nv = nt = 0
    def seg(lay, x0, y0, x1, y1):
        nonlocal nt
        if abs(x0-x1) < 1e-9 and abs(y0-y1) < 1e-9:
            return
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(round(x0*S)), int(round(y0*S))))
        t.SetEnd(pcbnew.VECTOR2I(int(round(x1*S)), int(round(y1*S))))
        t.SetWidth(int(TRACK_W*S))
        t.SetLayer(lay)
        t.SetNet(net)
        board.Add(t)
        nt += 1
    if pre is not None and pre[2] == path[0][0]:
        x, y = grid.xy(path[0][1], path[0][2])
        seg(path[0][0], pre[0], pre[1], x, y)
    if post is not None and post[2] == path[-1][0]:
        x, y = grid.xy(path[-1][1], path[-1][2])
        seg(path[-1][0], x, y, post[0], post[1])
    for k in range(1, len(runs)):
        lay, i, j = runs[k][0]
        x, y = grid.xy(i, j)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(round(x*S)), int(round(y*S))))
        v.SetWidth(int(VIA_DIA*S))
        v.SetDrill(int(VIA_DRILL*S))
        v.SetNet(net)
        board.Add(v)
        nv += 1
    for run in runs:
        for lay, i0, j0, i1, j1 in merge_run(run):
            if i0 == i1 and j0 == j1:
                continue
            p0 = grid.xy(i0, j0)
            p1 = grid.xy(i1, j1)
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(round(p0[0]*S)), int(round(p0[1]*S))))
            t.SetEnd(pcbnew.VECTOR2I(int(round(p1[0]*S)), int(round(p1[1]*S))))
            t.SetWidth(int(TRACK_W*S))
            t.SetLayer(lay)
            t.SetNet(net)
            board.Add(t)
            nt += 1
    return nt, nv, len(runs)

def fresh():
    return list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                      for p in fp.Pads()]

def make_grid(items):
    g = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
    g.build(items)
    return g

def starts_near(grid, pad, r=5):
    c = pad.GetPosition()
    ci, cj = grid.ij(c.x/S, c.y/S)
    cand = []
    for l in LAYERS:
        for di in range(-r, r+1):
            for dj in range(-r, r+1):
                i, j = ci+di, cj+dj
                if 0 <= i < grid.nx and 0 <= j < grid.ny and grid.OK[l][j, i]:
                    cand.append((di*di+dj*dj, (l, i, j)))
    cand.sort()
    return [c for _, c in cand[:8]]

# ------------------------------------------------------------ 3. the two nets
print("\n3. routing (sequential: each net sees the previous one's copper)", flush=True)
for name in ("ROW3", "ROW5"):
    pin = PIN[name]
    allc = fresh()
    grid = make_grid([it for it in allc if it.GetNetname() != name])
    tgt = [it for it in allc if it.GetNetname() == name
           and it.m_Uuid.AsString() not in j1a_pads]
    goals = {gc for gc in replan.cells_of(grid, tgt, LAYERS)
             if grid.OK[gc[0]][gc[2], gc[1]]}
    src = j1a.FindPadByNumber(str(pin))
    st = starts_near(grid, src)
    c = src.GetPosition()
    path, cross, exp, closest = probe.astar(grid, st, goals, 25.0, conflict=False)
    if path is None:
        print("   %-5s pin %-2d NO PATH (expanded %d, closest %.2fmm)"
              % (name, pin, exp, closest[0]*step), flush=True)
        continue
    ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
             for k in range(1, len(path))) * step
    # The pad is a shape, so a track ending anywhere inside it connects -- start
    # at its exact centre anyway so the emitted copper begins where the wire
    # visually should.  The far end lands on another *track*, which needs the
    # centreline treatment.
    pre = (c.x/S, c.y/S, path[0][0])
    p = grid.xy(path[-1][1], path[-1][2])
    post = attach_pt(p[0], p[1], tgt)
    if post is not None:
        post = (post[0], post[1], path[-1][0])
    nt, nv, nr = emit(board, name, grid, path, pre=pre, post=post)
    print("   %-5s pin %-2d @(%.2f,%.2f) -> %.1fmm  %d track(s) %d via(s) %d run(s)"
          % (name, pin, c.x/S, c.y/S, ln, nt, nv, nr), flush=True)

# ------------------------------------------------------------ 4. repair GND
def islands(items, netname):
    g = [it for it in items if it.GetNetname() == netname]
    par = list(range(len(g)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    def is_trk(it):
        return isinstance(it, pcbnew.PCB_TRACK) and not isinstance(it, pcbnew.PCB_VIA)

    def ends(it):
        s, e = it.GetStart(), it.GetEnd()
        return (s.x/S, s.y/S), (e.x/S, e.y/S)

    def box(it):
        bb = it.GetBoundingBox()
        return (bb.GetLeft()/S, bb.GetTop()/S, bb.GetRight()/S, bb.GetBottom()/S)

    def d_pt_seg(x, y, a, b):
        dx, dy = b[0]-a[0], b[1]-a[1]
        if dx == 0 and dy == 0:
            return math.hypot(x-a[0], y-a[1])
        t = max(0.0, min(1.0, ((x-a[0])*dx + (y-a[1])*dy) / (dx*dx+dy*dy)))
        return math.hypot(x-(a[0]+t*dx), y-(a[1]+t*dy))

    def d_ss(p, q, r, s):
        return min(d_pt_seg(p[0], p[1], r, s), d_pt_seg(q[0], q[1], r, s),
                   d_pt_seg(r[0], r[1], p, q), d_pt_seg(s[0], s[1], p, q))

    for a in range(len(g)):
        for b in range(a+1, len(g)):
            A, B = g[a], g[b]
            if is_trk(A) and is_trk(B):
                pa, qa = ends(A)
                pb, qb = ends(B)
                if d_ss(pa, qa, pb, qb) > A.GetWidth()/S/2 + B.GetWidth()/S/2 + 1e-9:
                    continue
            else:
                ax0, ay0, ax1, ay1 = box(A)
                bx0, by0, bx1, by1 = box(B)
                if not is_trk(A):
                    ax0, ay0, ax1, ay1 = ax0-0.1, ay0-0.1, ax1+0.1, ay1+0.1
                if not is_trk(B):
                    bx0, by0, bx1, by1 = bx0-0.1, by0-0.1, bx1+0.1, by1+0.1
                if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
                    continue
            uni(a, b)
    groups = {}
    for i in range(len(g)):
        groups.setdefault(find(i), []).append(i)
    return g, sorted(groups.values(), key=len, reverse=True)

print("\n4. repairing GND", flush=True)
allc = fresh()
g, groups = islands(allc, 'GND')
print("   GND now %d island(s), sizes %s"
      % (len(groups), [len(x) for x in groups[:8]]), flush=True)
main = groups[0]
# One grid for every repair: GND's own copper is not an obstacle, so bridging one
# orphan does not change the map for the next.
grid = make_grid([it for it in allc if it.GetNetname() != 'GND'])
goals = {gc for gc in replan.cells_of(grid, [g[i] for i in main], LAYERS)
         if grid.OK[gc[0]][gc[2], gc[1]]}
print("   main island %d item(s), %d goal cell(s)" % (len(main), len(goals)), flush=True)
repaired = 0
for grp in groups[1:]:
    # Start ON the island's own copper, exactly as the main-island goals are
    # built.  Starting on a *neighbouring* legal cell instead leaves the
    # emitted track beginning 0.1mm beside the island -- electrically touching
    # (KiCad connects overlapping copper) but with a free-hanging end, which is
    # what DRC reported as track_dangling on the first run.
    st = [c for c in replan.cells_of(grid, [g[i] for i in grp], LAYERS)
          if grid.OK[c[0]][c[2], c[1]]]
    if not st:
        for idx in grp:                       # copper too thin to cover a cell
            it = g[idx]
            if not isinstance(it, pcbnew.PCB_TRACK):
                continue
            s, e = it.GetStart(), it.GetEnd()
            for pt in (s, e):
                i, j = grid.ij(pt.x/S, pt.y/S)
                for l in LAYERS:
                    for di in (-1, 0, 1):
                        for dj in (-1, 0, 1):
                            a, b = i+di, j+dj
                            if (0 <= a < grid.nx and 0 <= b < grid.ny
                                    and grid.OK[l][b, a]):
                                st.append((l, a, b))
    st = list(dict.fromkeys(st))[:16]
    if not st:
        print("   island of %-2d: no legal start cell" % len(grp), flush=True)
        continue
    path, cross, exp, closest = probe.astar(grid, st, goals, 25.0, conflict=False)
    if path is None:
        print("   island of %-2d: NO PATH (closest %.2fmm)"
              % (len(grp), closest[0]*step), flush=True)
        continue
    ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
             for k in range(1, len(path))) * step
    p0 = grid.xy(path[0][1], path[0][2])
    p1 = grid.xy(path[-1][1], path[-1][2])
    a0 = attach_pt(p0[0], p0[1], [g[i] for i in grp])
    a1 = attach_pt(p1[0], p1[1], [g[i] for i in main])
    pre = (a0[0], a0[1], path[0][0]) if a0 else None
    post = (a1[0], a1[1], path[-1][0]) if a1 else None
    nt, nv, nr = emit(board, 'GND', grid, path, pre=pre, post=post)
    print("   island of %-2d -> main: %.1fmm  %d track(s) %d via(s)"
          % (len(grp), ln, nt, nv), flush=True)
    repaired += 1
print("   bridged %d orphan island(s)" % repaired, flush=True)

# ------------------------------------------------------------ 5. retire J1 4/6
j1 = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1'][0]
print("\n5. clearing the superseded J1 pads", flush=True)
for n in ("4", "6"):
    p = j1.FindPadByNumber(n)
    print("   J1 pad %s: was %s" % (n, p.GetNetname()), flush=True)
    p.SetNetCode(0)

pcbnew.SaveBoard(OUT, board)
print("\nsaved to %s" % OUT, flush=True)
