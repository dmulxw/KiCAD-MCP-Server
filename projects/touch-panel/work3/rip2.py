"""Stage 1b: rip by NET CLASS, not by region.  rip.py was too greedy.

comp.py showed the left gutter is not a fan-out channel at all -- it is GND's
bus (148 segments) plus COL0's vertical distribution spine (47).  Ripping the
spine is what shattered COL0 into 22 pieces; GND survived only because its zone
covers it.  Neither is replaceable from a header: a COLUMN net's whole job is to
run down the gutter and stub into 21 electrodes.

And the bottom strip does not need to be touched at all.  Everything the rip
would have taken from it lies at y > 241.5, while every trunk ends at y <= 235.8
(ROW20).  A route feeding a trunk from the side never goes near the strip.  So
keeping it costs nothing and leaves ~28 of the 40 nets as a single island,
with their old copper still hanging off the bottom as a free, already-connected
target.

Rip: ROW*/CSEL*/GND/+3V3 inside the left and right gutters only.
Keep: every COL* net, everywhere; the whole bottom strip; the array interior.
"""
import sys, os, math, collections
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E

S = 1e6
OUT = '_rip2.kicad_pcb'
GRAVE = []

STRIP_Y = 241.5
GUT_L, GUT_R = 104.2, 166.8
WIN = (100.30, 118.00, 102.40, 148.00)

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
E.widen(board)
print("loaded %d track(s), %d footprint(s)"
      % (len(list(board.GetTracks())), len(list(board.GetFootprints()))), flush=True)

# ---------------------------------------------------------------- 1. GND wall
x0, y0, x1, y1 = WIN
wall = [it for it in board.GetTracks()
        if it.GetNetname() == 'GND'
        and it.GetBoundingBox().GetLeft()/S >= x0
        and it.GetBoundingBox().GetRight()/S <= x1
        and it.GetBoundingBox().GetTop()/S >= y0
        and it.GetBoundingBox().GetBottom()/S <= y1]
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
print("3. FPC J1: %d footprint(s) removed" % len(j1), flush=True)
for fp in j1:
    board.Remove(fp)
    GRAVE.append(fp)

# ---------------------------------------------------------------- 4. the rip
def gutter(it):
    """Left or right gutter only.  The strip is deliberately NOT a region."""
    bb = it.GetBoundingBox()
    if bb.GetRight()/S < GUT_L:
        return "left gutter"
    if bb.GetLeft()/S > GUT_R:
        return "right gutter"
    return None


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
print("4. before:  %s" % (", ".join("%s=%d" % (n, before[n]) for n in nets
                                    if before[n] > 1) or "every net one island"),
      flush=True)

rip = collections.Counter()
kept = collections.Counter()
for it in list(board.GetTracks()):
    g = gutter(it)
    if not g:
        continue
    n = it.GetNetname()
    if n.startswith("COL"):
        kept[n] += 1          # the spine.  never rip this.
        continue
    board.Remove(it)
    GRAVE.append(it)
    rip[g] += 1
print("   ripped %d segment(s): %s" % (sum(rip.values()), dict(rip)), flush=True)
if kept:
    print("   kept %d COLUMN segment(s) in the gutters: %s"
          % (sum(kept.values()), dict(kept)), flush=True)

after = {n: islands(n) for n in nets}
bad = {n: (before[n], after[n]) for n in nets if after[n] > before[n]}
print("   after:   %s" % (", ".join("%s=%d" % (n, after[n]) for n in nets
                                    if after[n] > 1) or "every net one island"),
      flush=True)
print("   fragmented: %d  %s"
      % (len(bad), {k: "%d->%d" % v for k, v in sorted(bad.items())}), flush=True)

pcbnew.SaveBoard(OUT, board)
print("\nsaved to %s" % OUT, flush=True)
