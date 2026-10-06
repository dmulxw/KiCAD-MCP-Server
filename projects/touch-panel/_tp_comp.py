"""Connected free-space components for one net's masks; where can a trace go?"""
import importlib.util, sys, numpy as np, pcbnew
from collections import deque
spec = importlib.util.spec_from_file_location("R", "_tp_route.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
NET = sys.argv[1]
board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board); R.absorb(board, rt)
w = R.WIDTHS.get(NET, R.DEFAULT_W); hw = w/2.0
blocked, via_blocked = rt.blocked_for(NET, hw)

NB8 = ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))
def comp(seed_cells):
    seen = np.zeros_like(blocked); q = deque()
    for (l,i,j) in seed_cells:
        if not blocked[l,i,j] and not seen[l,i,j]:
            seen[l,i,j]=True; q.append((l,i,j))
    while q:
        l,i,j = q.popleft()
        for di,dj in NB8:
            i2,j2 = i+di, j+dj
            if 0<=i2<R.NX and 0<=j2<R.NY and not blocked[l,i2,j2] and not seen[l,i2,j2]:
                seen[l,i2,j2]=True; q.append((l,i2,j2))
        if not via_blocked[l,i,j]:
            l2 = 1-l
            if not blocked[l2,i,j] and not seen[l2,i,j]:
                seen[l2,i,j]=True; q.append((l2,i,j))
    return seen

for (x, y, tag) in [(float(a.split(":")[0]), float(a.split(":")[1]), a.split(":")[2])
                    for a in sys.argv[2:]]:
    i = int(round((x-R.OX)/R.GRID)); j = int(round((y-R.OY)/R.GRID))
    c = comp([(0,i,j),(1,i,j)] if not blocked[0,i,j] or not blocked[1,i,j] else [])
    n = int(c.sum())
    print("\n%s (%.3f,%.3f)  blockedF=%s blockedB=%s  component=%d cells"
          % (tag, x, y, blocked[0,i,j], blocked[1,i,j], n))
    if n == 0: continue
    idx = np.argwhere(c)
    print("   bbox x %.2f..%.2f  y %.2f..%.2f  layers %s"
          % (R.mx(idx[:,1].min()), R.mx(idx[:,1].max()),
             R.my(idx[:,2].min()), R.my(idx[:,2].max()), sorted(set(idx[:,0].tolist()))))
    # for each y row in the bbox, does this component have any cell in x 98..106?
    print("   rows where the component spans x 98..106 (a crossing):")
    hits = []
    for jj in range(int((98-R.OX)/R.GRID), int((106-R.OX)/R.GRID)):
        pass
    for jj in range(idx[:,2].min(), idx[:,2].max()+1):
        xs = idx[idx[:,2]==jj][:,1]
        lo, hi = R.mx(xs.min()), R.mx(xs.max())
        if lo < 99.5 and hi > 104.0:
            hits.append((R.my(jj), lo, hi, sorted(set(idx[idx[:,2]==jj][:,0].tolist()))))
    if not hits:
        print("      (none)")
    for (yy, lo, hi, ls) in hits[:40]:
        print("      y=%7.2f  spans x %.2f..%.2f  L%s" % (yy, lo, hi, ls))
