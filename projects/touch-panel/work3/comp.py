"""Who owns the copper the rip removed, region by region?

COL0 shattered into 22 pieces while GND did not move at all, which says the
gutters are not uniform: part of what is in them is the FPC fan-out (replaceable
from an edge header) and part is the column distribution (not replaceable).
Never destroy the second kind.
"""
import sys, os, collections
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E

S = 1e6
STRIP_Y = 241.5
GUT_L, GUT_R = 104.2, 166.8

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
E.widen(board)
GRAVE = []

def region(it):
    bb = it.GetBoundingBox()
    l, t, r, b = bb.GetLeft()/S, bb.GetTop()/S, bb.GetRight()/S, bb.GetBottom()/S
    if t > STRIP_Y:
        return "strip"
    if r < GUT_L:
        return "Lgutter"
    if l > GUT_R:
        return "Rgutter"
    return None

cnt = collections.defaultdict(collections.Counter)
tot = collections.Counter()
for it in board.GetTracks():
    r = region(it)
    if r:
        cnt[it.GetNetname()][r] += 1
        tot[r] += 1

print("removed per region: %s   total %d\n" % (dict(tot), sum(tot.values())))
print("%-9s %7s %7s %7s   %s" % ("net", "strip", "Lgutter", "Rgutter", "kind"))
for n in sorted(cnt, key=lambda k: -sum(cnt[k].values())):
    c = cnt[n]
    kind = "COLUMN distribution" if n.startswith("COL") else "fan-out"
    print("%-9s %7d %7d %7d   %s"
          % (n, c["strip"], c["Lgutter"], c["Rgutter"], kind))

print("\ntotals by kind:")
for kind, pref in (("COLUMN", "COL"), ("ROW/CSEL/power", None)):
    s = sum(sum(c.values()) for n, c in cnt.items()
            if (n.startswith(pref) if pref else not n.startswith("COL")))
    print("   %-16s %d" % (kind, s))
