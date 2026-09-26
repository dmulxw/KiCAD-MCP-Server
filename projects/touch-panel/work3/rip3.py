"""Stage 1c: also clear the strip -- but never clear a net out of existence.

diag18.py found the seven nets that block the whole interface change:

    CSEL0 CSEL1 CSEL2 CSEL7 CSEL8 CSEL9 +3V3

Their copper bbox is y 241.4..248.1 -- inside the bottom strip, nowhere else.
No in-array distribution at all; the FPC was their only feed.  Compare CSEL3,
which spans y 100.7..249.5 and is comfortably reachable: it owns a real line in
the array, so the strip is merely a second home for it.

That is the rule this script applies.  A net whose copper lives ONLY in the
strip cannot be ripped from the strip -- rip its pocket and the net ceases to
exist.  Everyone else's strip copper is redundant (it is what made 18 nets split
1->2 in rip2: the strip piece has no pad on it), and it is precisely what stands
between those seven pockets and the gutter corridor that has to reach them.

So:
  COL*            keep everywhere  (the gutter spine; rip.py's fatal mistake)
  strip-only nets keep the strip    (else the net is destroyed)
  everything else rip gutters + strip
"""
import sys, os, math, collections
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E

S = 1e6
OUT = '_rip3.kicad_pcb'
GRAVE = []

STRIP_Y = 241.5
GUT_L, GUT_R = 104.2, 166.8
STRIP_ONLY_Y = 238.0     # bbox min y above this means "lives in the strip"
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

# ---------------------------------------------------------------- 4. classify
# A net is strip-only when every piece of its copper has bbox min-y in the
# strip.  Computed on what is left after the FPC is gone, which is the set of
# copper that has to keep working.
tracks = [it for it in board.GetTracks()]
mins = collections.defaultdict(lambda: 1e9)
for it in tracks:
    n = it.GetNetname()
    if n:
        mins[n] = min(mins[n], it.GetBoundingBox().GetTop()/S)
strip_only = {n for n, m in mins.items() if m >= STRIP_ONLY_Y}
print("4. strip-only nets (their whole copper is in the strip): %s"
      % " ".join(sorted(strip_only)), flush=True)


def region(it):
    bb = it.GetBoundingBox()
    if bb.GetTop()/S > STRIP_Y:
        return "strip"
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
print("   before: %s" % (", ".join("%s=%d" % (n, before[n]) for n in nets
                                   if before[n] > 1) or "every net one island"),
      flush=True)

rip = collections.Counter()
for it in list(board.GetTracks()):
    r = region(it)
    if not r:
        continue
    n = it.GetNetname()
    if n.startswith("COL"):
        continue
    if r == "strip" and n in strip_only:
        continue
    board.Remove(it)
    GRAVE.append(it)
    rip[r] += 1
print("   ripped %d segment(s): %s" % (sum(rip.values()), dict(rip)), flush=True)

after = {n: islands(n) for n in nets}
bad = {n: (before[n], after[n]) for n in nets if after[n] > before[n]}
print("   after:  %s" % (", ".join("%s=%d" % (n, after[n]) for n in nets
                                   if after[n] > 1) or "every net one island"),
      flush=True)
print("   fragmented: %d  %s"
      % (len(bad), {k: "%d->%d" % v for k, v in sorted(bad.items())}), flush=True)
print("   the seven: %s"
      % {n: after[n] for n in sorted(strip_only)}, flush=True)

pcbnew.SaveBoard(OUT, board)
print("\nsaved to %s" % OUT, flush=True)
