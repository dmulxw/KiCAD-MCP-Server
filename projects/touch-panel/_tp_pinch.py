"""How close does the main free region come to the pocket that holds the R pads?"""
import importlib.util, sys, numpy as np, pcbnew
from collections import deque
spec = importlib.util.spec_from_file_location("R", "_tp_route.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
NET = sys.argv[1] if len(sys.argv) > 1 else "ROW17"
board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board); R.absorb(board, rt)
hw = R.WIDTHS.get(NET, R.DEFAULT_W) / 2.0
blocked, via_blocked = rt.blocked_for(NET, hw)

NB8 = ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))
def comp(l0,i0,j0):
    seen = np.zeros_like(blocked); q = deque()
    if not blocked[l0,i0,j0]:
        seen[l0,i0,j0]=True; q.append((l0,i0,j0))
    while q:
        l,i,j = q.popleft()
        for di,dj in NB8:
            i2,j2=i+di,j+dj
            if 0<=i2<R.NX and 0<=j2<R.NY and not blocked[l,i2,j2] and not seen[l,i2,j2]:
                seen[l,i2,j2]=True; q.append((l,i2,j2))
        if not via_blocked[l,i,j]:
            l2=1-l
            if not blocked[l2,i,j] and not seen[l2,i,j]:
                seen[l2,i,j]=True; q.append((l2,i,j))
    return seen

def cell(x,y): return int(round((x-R.OX)/R.GRID)), int(round((y-R.OY)/R.GRID))
wi,wj = cell(97.675,217.445); pi,pj = cell(101.59,216.6)
W = comp(0,wi,wj) | comp(1,wi,wj)
P = comp(0,pi,pj) | comp(1,pi,pj)
print("main=%d cells   pocket=%d cells   overlap=%d" % (W.sum(), P.sum(), (W&P).sum()))

# where do the two come closest?  For each row, the interval sets in x 95..112.
i_lo, i_hi = cell(95.0,0)[0], cell(112.0,0)[0]
best = []
for j in range(R.NY):
    wrow = np.nonzero(W[:, i_lo:i_hi+1].any(axis=0))[0]
    prow = np.nonzero(P[:, i_lo:i_hi+1].any(axis=0))[0]
    if len(wrow)==0 or len(prow)==0: continue
    we, pw = wrow.max()+i_lo, prow.min()+i_lo
    if we >= pw: continue          # they meet in this row (in x)
    best.append((R.my(j), R.mx(we), R.mx(pw), R.mx(pw)-R.mx(we)))
best.sort(key=lambda r: r[3])
print("\nclosest approaches in x (main east edge -> pocket west edge):")
for (y, a, b, g) in best[:20]:
    print("   y=%7.2f  main ends %.2f, pocket starts %.2f   gap %.2f mm" % (y,a,b,g))
print("\nrows where they are within 1.0 mm:")
for (y,a,b,g) in best:
    if g <= 1.0: print("   y=%7.2f  gap %.2f mm  (main->%.2f  pocket->%.2f)" % (y,g,a,b))
