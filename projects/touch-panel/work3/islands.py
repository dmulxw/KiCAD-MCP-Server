import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
S = 1e6

def seg(it):
    s, e = it.GetStart(), it.GetEnd()
    return (s.x/S, s.y/S, e.x/S, e.y/S)

def islands(board, name):
    items = []
    for t in board.GetTracks():
        if t.GetNetname() == name:
            items.append(('trk', t))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == name:
                items.append(('pad', p, fp.GetReference(), p.GetNumber()))
    n = len(items)
    par = list(range(n))
    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a
    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: par[rb] = ra
    def onl(it, lay):
        return it.IsOnLayer(lay)
    # track-to-track: same layer, distance <= sum of half widths (touching)
    for i in range(n):
        for j in range(i+1, n):
            ai, aj = items[i], items[j]
            if ai[0] == 'trk' and aj[0] == 'trk':
                ta, tb = ai[1], aj[1]
                if not any(onl(ta, l) and onl(tb, l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)):
                    continue
                x0,y0,x1,y1 = seg(ta); u0,v0,u1,v1 = seg(tb)
                ra_ = ta.GetWidth()/S/2; rb_ = tb.GetWidth()/S/2
                # endpoint-to-endpoint or endpoint-to-segment
                def d2seg(px,py,ax,ay,bx,by):
                    dx,dy = bx-ax, by-ay
                    L2 = dx*dx+dy*dy
                    if L2 == 0: return ((px-ax)**2+(py-ay)**2)**0.5
                    t = max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/L2))
                    return ((px-(ax+t*dx))**2+(py-(ay+t*dy))**2)**0.5
                dmin = min(d2seg(x0,y0,u0,v0,u1,v1), d2seg(x1,y1,u0,v0,u1,v1),
                           d2seg(u0,v0,x0,y0,x1,y1), d2seg(u1,v1,x0,y0,x1,y1))
                if dmin <= ra_ + rb_ + 0.001: uni(i,j)
            elif ai[0] == 'pad' or aj[0] == 'pad':
                k = i if ai[0]=='pad' else j
                m = j if ai[0]=='pad' else i
                if items[m][0] != 'trk': 
                    pad_a = items[m][1]; pad_b = items[k][1]
                    # pad-pad: overlapping bboxes
                    ba, bbx = pad_a.GetBoundingBox(), pad_b.GetBoundingBox()
                    if (ba.GetLeft() < bbx.GetRight() and bbx.GetLeft() < ba.GetRight()
                        and ba.GetTop() < bbx.GetBottom() and bbx.GetTop() < ba.GetBottom()):
                        uni(i,j)
                    continue
                pad = items[k][1]; trk = items[m][1]
                if not (pad.IsOnLayer(trk.GetLayer())): continue
                bx0,by0,bx1,by1 = seg(trk)
                bb = pad.GetBoundingBox()
                # pad bbox expanded by track half width vs segment
                def seg_box_hit(ax,ay,bx,by, L,T,R,B, rr):
                    L,T,R,B = L-rr, T-rr, R+rr, B+rr
                    if max(ax,bx) < L or min(ax,bx) > R: return False
                    if max(ay,by) < T or min(ay,by) > B: return False
                    return True
                if seg_box_hit(bx0,by0,bx1,by1, bb.GetLeft()/S, bb.GetTop()/S,
                               bb.GetRight()/S, bb.GetBottom()/S, trk.GetWidth()/S/2):
                    uni(i,j)
    groups = {}
    for k in range(n):
        groups.setdefault(find(k), []).append(k)
    return items, groups

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
for name in ('ROW3', 'ROW5'):
    items, groups = islands(board, name)
    print("=== %s : %d item(s), %d island(s) ===" % (name, len(items), len(groups)))
    for gi, (root, ks) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1]))):
        xs0=ys0=1e9; xs1=ys1=-1e9; nt=0
        labels=[]
        for k in ks:
            it = items[k]
            if it[0]=='trk':
                nt += 1
                a,b,c,d = seg(it[1])
                xs0=min(xs0,a,c); xs1=max(xs1,a,c); ys0=min(ys0,b,d); ys1=max(ys1,b,d)
            else:
                it2 = it[1]; bb=it2.GetBoundingBox()
                xs0=min(xs0,bb.GetLeft()/S); xs1=max(xs1,bb.GetRight()/S)
                ys0=min(ys0,bb.GetTop()/S); ys1=max(ys1,bb.GetBottom()/S)
                labels.append("%s.%s" % (it[2], it[3]))
        print("  island %d: %3d item(s) (%d trk, %d pad)  x %8.3f..%8.3f  y %8.3f..%8.3f"
              % (gi, len(ks), nt, len(ks)-nt, xs0, xs1, ys0, ys1))
        if labels:
            print("      pads: %s" % (", ".join(labels[:12]) + (" ..." if len(labels)>12 else "")))
    print()
