"""Stage 1 of the two-header rebuild: clear the ground, then stop and look.

Every earlier attempt (edgeflood, _band 162/29, honest) tried to route 40 new
nets into a board that still carried all 40 old nets' fan-out as obstacles.
That is twice the copper in the same gutters, and it is why they collapsed.

The fan-out is what seals the trunks.  Measured on _final.kicad_pcb: ROW15's
trunk begins at (101.590, 203.800) and the nearest reachable F.Cu cell is
(100.550, 203.750) -- 1.00mm short, with a GND F.Cu vertical at x=101.219 in
between.  Both headers exhausted the whole grid (1.6M / 2.0M cells) and stopped
on that same cell.  The gutter itself is passable -- B.Cu keeps a continuous
1.30mm free lane at every height from y=118 to y=242 -- but the trunk ENDS are
inside the comb, and a comb of 0.2mm verticals at 0.40mm pitch has no lateral
gap at all.

So: J1 goes away, the fan-out goes away, and the two edge headers get a clean
board to route into.  This script does the destructive half only and writes a
checkpoint.  It does not route.
"""
import sys, os, collections
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E

S = 1e6
OUT = '_rip.kicad_pcb'
GRAVE = []

# The plan's regions, unchanged.
STRIP_Y = 241.5          # below the electrode array
GUT_L, GUT_R = 104.2, 166.8   # the array's own x span

WIN = (100.30, 118.00, 102.40, 148.00)   # the GND wall final.py removed

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
E.widen(board)
print("loaded %d track(s), %d footprint(s)"
      % (len(list(board.GetTracks())), len(list(board.GetFootprints()))), flush=True)

# ---------------------------------------------------------------- 1. GND wall
x0, y0, x1, y1 = WIN
wall = []
for it in board.GetTracks():
    if it.GetNetname() != 'GND':
        continue
    bb = it.GetBoundingBox()
    if (bb.GetLeft()/S >= x0 and bb.GetRight()/S <= x1
            and bb.GetTop()/S >= y0 and bb.GetBottom()/S <= y1):
        wall.append(it)
print("1. GND wall: %d segment(s)" % len(wall), flush=True)
for it in wall:
    board.Remove(it)
    GRAVE.append(it)

# ---------------------------------------------------------------- 2. headers
E.place(board, "J1A", E.HDR_LIB, E.HDR_FP, E.LEFT_X, E.LEFT_Y, {})
E.place(board, "J1B", E.HDR_LIB, E.HDR_FP, E.RIGHT_X, E.RIGHT_Y, {})
print("2. J1A @(%.2f,%.2f)  J1B @(%.2f,%.2f)"
      % (E.LEFT_X, E.LEFT_Y, E.RIGHT_X, E.RIGHT_Y), flush=True)

# ---------------------------------------------------------------- 3. the FPC
j1 = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1']
print("3. FPC J1: %d footprint(s) found" % len(j1), flush=True)
for fp in j1:
    board.Remove(fp)
    GRAVE.append(fp)

# ---------------------------------------------------------------- 4. fan-out
def region(it):
    bb = it.GetBoundingBox()
    l, t, r, b = bb.GetLeft()/S, bb.GetTop()/S, bb.GetRight()/S, bb.GetBottom()/S
    if t > STRIP_Y:
        return "bottom strip"
    if r < GUT_L:
        return "left gutter"
    if l > GUT_R:
        return "right gutter"
    return None

# Snapshot per net BEFORE ripping, so island loss can be attributed.
def islands(netname):
    g = [it for it in board.GetTracks() if it.GetNetname() == netname]
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
    import math
    def is_trk(it):
        return not isinstance(it, pcbnew.PCB_VIA)
    def ends(it):
        s, e = it.GetStart(), it.GetEnd()
        return (s.x/S, s.y/S), (e.x/S, e.y/S)
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
            pa, qa = ends(A)
            pb, qb = ends(B)
            if d_ss(pa, qa, pb, qb) > A.GetWidth()/S/2 + B.GetWidth()/S/2 + 1e-9:
                continue
            uni(a, b)
    return len({find(i) for i in range(len(g))})

nets = sorted({it.GetNetname() for it in board.GetTracks() if it.GetNetname()})
before = {n: islands(n) for n in nets}
print("4. islands before the rip: %s"
      % ", ".join("%s=%d" % (n, before[n]) for n in nets
                  if before[n] > 1) or "   (every net already one island)", flush=True)

rip = collections.Counter()
n = 0
for it in list(board.GetTracks()):
    r = region(it)
    if r:
        board.Remove(it)
        GRAVE.append(it)
        rip[r] += 1
        n += 1
print("   removed %d track(s): %s" % (n, dict(rip)), flush=True)

after = {n2: islands(n2) for n2 in nets}
print("   islands after the rip:  %s"
      % ", ".join("%s=%d" % (n2, after[n2]) for n2 in nets if after[n2] > 1),
      flush=True)
worse = {n2: (before[n2], after[n2]) for n2 in nets if after[n2] > before[n2]}
print("   nets fragmented by the rip: %d  %s"
      % (len(worse), {k: "%d->%d" % v for k, v in sorted(worse.items())}), flush=True)

pcbnew.SaveBoard(OUT, board)
print("\nsaved to %s" % OUT, flush=True)
