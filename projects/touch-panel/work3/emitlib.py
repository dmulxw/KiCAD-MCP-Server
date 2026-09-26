"""final.py's emitter, lifted into an importable module.

final.py cannot be imported.  It has no __main__ guard: lines 31-170 load a
board, remove the GND wall, place J1A, route ROW3/ROW5 and SaveBoard to
_final.kicad_pcb.  `import final` would therefore re-run that whole stage and
overwrite the one board in this project that is known good.

The functions below are copied verbatim; the only change is that the five
globals they close over (board, step, TRACK_W, VIA_DIA, VIA_DRILL) become module
state set by bind() instead of script-level constants.
"""
import pcbnew
import edgeflood as E          # noqa: F401  (kept so callers can reach E)
import replan, probe           # noqa: F401

S = 1e6
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

# --------------------------------------------------------------- module state
board = None
step = 0.1
safety = 0.04
clearance = 0.2
TRACK_W, VIA_DIA, VIA_DRILL = 0.2, 0.6, 0.3
keep = pad_keep = egk = vek = 0.0

_graveyard = []          # board.Remove() hands the object to Python; if the
                         # proxy is GC'd SWIG loses its process-wide type table


def bind(bd, st=0.1, trk=0.2, safety_=0.04, clearance_=0.2):
    """Point the module at a board and derive the grid keeps from its rules."""
    global board, step, safety, clearance, TRACK_W, keep, pad_keep, egk, vek
    board, step = bd, st
    safety, clearance, TRACK_W = safety_, clearance_, trk
    edge_clear = bd.GetDesignSettings().m_CopperEdgeClearance / S
    keep = clearance + TRACK_W/2 + safety
    pad_keep = clearance + 0.3 + safety
    egk = edge_clear + clearance + safety
    vek = egk + 0.3


def kill(item):
    board.Remove(item)
    _graveyard.append(item)


# ------------------------------------------------------------------ emitter
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
            segs.append((run[0][0], start[1], start[2],
                         run[k-1][1], run[k-1][2]))
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
    width are still two separate islands.
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


def via_here(name, x, y):
    """A via of this net already sitting at (x, y)?

    emit() drops a via at the head of every run after the first without asking
    whether one is already there.  Two bridges for the same net that change
    layer at the same cell -- or a bridge whose layer change lands on a via an
    earlier bridge placed -- then produce two coincident vias, which DRC calls
    holes_co_located.  Measured: 10 of them on _t2, exactly matching 10
    duplicated (net, x, y) vias, where _r2 had none.

    Skipping the second one is safe: the runs it joins are already joined by
    the via that is there, on the same net, spanning the same layers.
    """
    xi, yi = int(round(x * S)), int(round(y * S))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == name:
            p = t.GetPosition()
            if p.x == xi and p.y == yi:
                return True
    return False


def emit(name, grid, path, pre=None, post=None):
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
        if via_here(name, x, y):
            continue
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


# ------------------------------------------------------------------ helpers
def fresh():
    return list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                      for p in fp.Pads()]


def netcopper(name):
    """Everything on this net except the header pads themselves.

    The header pads are on the net, but they are the *ends* of routes, not the
    places routes want to reach.  Leaving them in the goal set makes A* return a
    one-cell path back to the pin we started from.
    """
    refs = {fp.m_Uuid.AsString() for fp in board.GetFootprints()
            if fp.GetReference() in ("J1A", "J1B")}
    out = []
    for it in fresh():
        if it.GetNetname() != name:
            continue
        if isinstance(it, pcbnew.PAD) and it.GetParent().m_Uuid.AsString() in refs:
            continue
        out.append(it)
    return out


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


def goals_of(grid, items):
    return {gc for gc in replan.cells_of(grid, items, LAYERS)
            if grid.OK[gc[0]][gc[2], gc[1]]}
