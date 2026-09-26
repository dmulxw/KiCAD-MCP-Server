"""Is the GND wall at R4.1 / R6 the whole story?

Measured with the wall in place, ROW3's every pin was 96.9mm away and the
length grew by exactly 2.54mm per pin, i.e. every route ran the same corridor
over the top of the board.  The wall's two vertical runs plus a horizontal bar
leave 0.201mm and 0.234mm of clearance where 0.40mm is needed.

So: remove the GND copper in that window and re-measure.  If the hop collapses
to ~10mm the wall was the entire problem -- which is what the user said at the
outset ("先拆掉 x~100.55-101.35、y=128 那道 0.9mm 的 GND 墙").

Also reports whether GND survives as one connected island, because a wall is
only removable if it is a spur and not a link.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
WIN = (100.30, 118.00, 102.40, 148.00)      # x0, y0, x1, y1
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
TRACK_W = 0.2
board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
E.widen(board)          # <-- without this J1A sits outside the grid and every
                        #     index goes negative, wrapping to the far east side
j1a = E.place(board, "J1A", E.HDR_LIB, E.HDR_FP, E.LEFT_X, E.LEFT_Y, None)
J1A_PADS = {p.m_Uuid.AsString() for p in j1a.Pads()}
ALL0 = list(board.GetTracks()) + [p for fp in board.GetFootprints() for p in fp.Pads()]

x0, y0, x1, y1 = WIN
wall = []
for it in ALL0:
    if it.GetNetname() != 'GND':
        continue
    bb = it.GetBoundingBox()
    L, T, R, B = bb.GetLeft()/S, bb.GetTop()/S, bb.GetRight()/S, bb.GetBottom()/S
    if L >= x0 and R <= x1 and T >= y0 and B <= y1:
        wall.append(it)
print("GND items fully inside the window: %d" % len(wall))
for it in wall:
    if isinstance(it, pcbnew.PCB_TRACK):
        s, e = it.GetStart(), it.GetEnd()
        print("   %-4s (%8.3f,%8.3f)->(%8.3f,%8.3f)  w=%.2f"
              % ('VIA' if isinstance(it, pcbnew.PCB_VIA) else 'trk',
                 s.x/S, s.y/S, e.x/S, e.y/S, it.GetWidth()/S))

# ---- GND connectivity, before and after
def gnd_islands(items):
    """Union-find over GND copper: tracks join when the gap between their
    segments is <= the sum of their half-widths; pads join on bbox overlap."""
    import math
    g = [it for it in items if it.GetNetname() == 'GND']
    par = list(range(len(g)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    def is_trk(it):
        return isinstance(it, pcbnew.PCB_TRACK) and not isinstance(it, pcbnew.PCB_VIA)

    def s_(it):
        s, e = it.GetStart(), it.GetEnd()
        return (s.x/S, s.y/S, e.x/S, e.y/S)

    def box(it):
        bb = it.GetBoundingBox()
        return (bb.GetLeft()/S, bb.GetTop()/S, bb.GetRight()/S, bb.GetBottom()/S)

    def d_seg_seg(p, q, r, s):
        def d_pt_seg(x, y, a, b):
            dx, dy = b[0]-a[0], b[1]-a[1]
            if dx == 0 and dy == 0:
                return math.hypot(x-a[0], y-a[1])
            t = max(0.0, min(1.0, ((x-a[0])*dx + (y-a[1])*dy) / (dx*dx+dy*dy)))
            return math.hypot(x-(a[0]+t*dx), y-(a[1]+t*dy))
        return min(d_pt_seg(p[0], p[1], r, s), d_pt_seg(q[0], q[1], r, s),
                   d_pt_seg(r[0], r[1], p, q), d_pt_seg(s[0], s[1], p, q))

    for a in range(len(g)):
        for b in range(a+1, len(g)):
            A, B = g[a], g[b]
            if is_trk(A) and is_trk(B):
                ha, hb = A.GetWidth()/S/2, B.GetWidth()/S/2
                pa, qa = s_(A)[:2], s_(A)[2:]
                pb, qb = s_(B)[:2], s_(B)[2:]
                if d_seg_seg(pa, qa, pb, qb) > ha + hb + 1e-9:
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
    return g, groups

for tag, items in (("before", ALL0), ("after", [it for it in ALL0 if it not in wall])):
    g, groups = gnd_islands(items)
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    print("GND %-6s: %d island(s)  sizes %s" % (tag, len(groups), sizes[:8]))

# ---- re-measure
step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

for tag, items in (("WALL IN PLACE", ALL0),
                   ("WALL REMOVED", [it for it in ALL0 if it not in wall])):
    print("\n### %s" % tag)
    for name in ("ROW3", "ROW5"):
        ob = [it for it in items if it.GetNetname() != name
              and it.m_Uuid.AsString() not in J1A_PADS]
        grid = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
        grid.build(ob)
        tgt = [it for it in items if it.GetNetname() == name
               and it.m_Uuid.AsString() not in J1A_PADS]
        goals = {gc for gc in replan.cells_of(grid, tgt, LAYERS)
                 if grid.OK[gc[0]][gc[2], gc[1]]}
        out = []
        for n in range(1, 21):
            pad = j1a.FindPadByNumber(str(n))
            c = pad.GetPosition(); ci, cj = grid.ij(c.x/S, c.y/S)
            cand = []
            for l in LAYERS:
                for di in range(-5, 6):
                    for dj in range(-5, 6):
                        i, j = ci+di, cj+dj
                        if 0 <= i < grid.nx and 0 <= j < grid.ny and grid.OK[l][j, i]:
                            cand.append((di*di+dj*dj, (l, i, j)))
            cand.sort()
            st = [c for _, c in cand[:8]]
            if not st:
                continue
            path, cross, exp, closest = probe.astar(grid, st, goals, 25.0, conflict=False)
            if path is None:
                out.append((n, None))
                continue
            ln = sum(((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
                     for k in range(1, len(path))) * step
            out.append((n, ln))
        ok = sorted([(l, n) for n, l in out if l is not None])
        print("  %-5s  best %s  |  %s" % (
            name, " ".join("pin%d %.1fmm" % (n, l) for l, n in ok[:5]),
            " ".join("pin%d %.1f" % (n, l) for l, n in ok[5:10])), flush=True)
