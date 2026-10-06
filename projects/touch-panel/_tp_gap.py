"""Minimum separation between the main free region and the pocket, and the blocker between."""
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
    if not blocked[l0,i0,j0]: seen[l0,i0,j0]=True; q.append((l0,i0,j0))
    while q:
        l,i,j = q.popleft()
        for di,dj in NB8:
            i2,j2=i+di,j+dj
            if 0<=i2<R.NX and 0<=j2<R.NY and not blocked[l,i2,j2] and not seen[l,i2,j2]:
                seen[l,i2,j2]=True; q.append((l2:=(l),i2,j2)[1:]) if False else q.append((l,i2,j2))
        if not via_blocked[l,i,j]:
            l2=1-l
            if not blocked[l2,i,j] and not seen[l2,i,j]:
                seen[l2,i,j]=True; q.append((l2,i,j))
    return seen

def cell(x,y): return int(round((x-R.OX)/R.GRID)), int(round((y-R.OY)/R.GRID))
wi,wj = cell(97.675,217.445); pi,pj = cell(101.59,216.6)
W = comp(0,wi,wj) | comp(1,wi,wj)
P = np.zeros_like(W)
P[0,pi,pj] = True
P = comp(0,pi,pj) | comp(1,pi,pj)
WP = W.any(axis=0); PP = P.any(axis=0)

# BFS over ALL cells from W; stop at the first P cell. 8-connected => Chebyshev steps.
dist = np.full((R.NX,R.NY), -1, dtype=np.int32)
par  = {}
q = deque()
for (i,j) in np.argwhere(WP):
    dist[i,j]=0; q.append((i,j))
found = None
while q:
    i,j = q.popleft()
    if PP[i,j]:
        found = (i,j); break
    for di,dj in NB8:
        i2,j2=i+di,j+dj
        if 0<=i2<R.NX and 0<=j2<R.NY and dist[i2,j2]<0:
            dist[i2,j2]=dist[i,j]+1; par[(i2,j2)]=(i,j); q.append((i2,j2))
print("main=%d  pocket=%d" % (W.sum(), P.sum()))
if found is None:
    print("no path found at all"); sys.exit(0)
i,j = found
print("closest pocket cell: (%.2f,%.2f)  steps=%d  approx %.2f mm"
      % (R.mx(i), R.my(j), dist[i,j], dist[i,j]*R.GRID))
path=[]
c=(i,j)
while c in par:
    path.append(c); c=par[c]
path.append(c); path.reverse()
print("path from main -> pocket (%d cells, both-layer):" % len(path))
for n,(ci,cj) in enumerate(path):
    print("   %-24s F=%-5s B=%-5s  via_ok=%-5s"
          % ("%.2f,%.2f" % (R.mx(ci),R.my(cj)), blocked[0,ci,cj], blocked[1,ci,cj],
             not (via_blocked[0,ci,cj] or via_blocked[1,ci,cj])))
    if n>14: print("   ... (%d more)" % (len(path)-15)); break
