"""Every pair of tracks on the board closer than the 0.2mm rule.

Bins items by 3mm cell so only genuine neighbours are tested, then does exact
segment-to-segment distance. Reports the closest approach and where it is, so
the emitter's defect can be located instead of guessed at.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew

S = 1e6
R = 0.2
board = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else '_honest.kicad_pcb')

tr = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    s, e = t.GetStart(), t.GetEnd()
    tr.append(dict(u=t.m_Uuid.AsString(), net=t.GetNetname(),
                   x0=s.x/S, y0=s.y/S, x1=e.x/S, y1=e.y/S,
                   w=t.GetWidth()/S, lay=t.GetLayerName()))
print("tracks: %d  (SAME-LAYER pairs only)" % len(tr))

def seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    """Min distance between segment AB and CD, and the two closest points."""
    ux, uy = bx-ax, by-ay
    vx, vy = dx-cx, dy-cy
    wx, wy = ax-cx, ay-cy
    a = ux*ux+uy*uy; b = ux*vx+uy*vy; c = vx*vx+vy*vy
    d = ux*wx+uy*wy; e = vx*wx+vy*wy
    D = a*c-b*b
    if D < 1e-18:
        s = 0.0
        t = (e/c) if c > 1e-18 else 0.0
    else:
        s = (b*e-c*d)/D
        t = (a*e-b*d)/D
    s = min(1.0, max(0.0, s)); t = min(1.0, max(0.0, t))
    # re-clamp once (segments, not lines)
    s2 = min(1.0, max(0.0, (b*t+d)/a if a > 1e-18 else 0.0))
    t2 = min(1.0, max(0.0, (b*s2+e)/c if c > 1e-18 else 0.0))
    px, py = ax+s2*ux, ay+s2*uy
    qx, qy = cx+t2*vx, cy+t2*vy
    return ((px-qx)**2+(py-qy)**2)**0.5, px, py, qx, qy

BIN = 3.0
grid = {}
for k, t in enumerate(tr):
    gx0 = int(min(t['x0'], t['x1'])//BIN); gx1 = int(max(t['x0'], t['x1'])//BIN)
    gy0 = int(min(t['y0'], t['y1'])//BIN); gy1 = int(max(t['y0'], t['y1'])//BIN)
    for gx in range(gx0, gx1+1):
        for gy in range(gy0, gy1+1):
            grid.setdefault((gx, gy), []).append(k)

bad = {}
seen = set()
for (gx, gy), ks in grid.items():
    for ii in range(len(ks)):
        for jj in range(ii+1, len(ks)):
            a, b = ks[ii], ks[jj]
            if (a, b) in seen:
                continue
            seen.add((a, b))
            ta, tb = tr[a], tr[b]
            if ta['net'] == tb['net'] or ta['lay'] != tb['lay']:
                continue
            reach = (ta['w']+tb['w'])/2 + 0.5
            if (max(ta['x0'], ta['x1'], tb['x0'], tb['x1'])
                    - min(ta['x0'], ta['x1'], tb['x0'], tb['x1']) > reach + 5.0):
                pass
            dist, px, py, qx, qy = seg_seg(ta['x0'], ta['y0'], ta['x1'], ta['y1'],
                                           tb['x0'], tb['y0'], tb['x1'], tb['y1'])
            edge = dist - (ta['w']+tb['w'])/2
            if edge < R - 1e-9:
                key = (ta['net'], tb['net'])
                rec = bad.setdefault(key, [0, 1e9, None])
                rec[0] += 1
                if edge < rec[1]:
                    rec[1] = edge
                    rec[2] = (px, py, qx, qy, ta['lay'], tb['lay'],
                              ta['w'], tb['w'], ta['u'][:8], tb['u'][:8])
for key in sorted(bad, key=lambda k: bad[k][1]):
    n, edge, g = bad[key]
    print("%-8s/%-8s  n=%-3d closest edge %+.4fmm  at (%.3f,%.3f)-(%.3f,%.3f)  %s/%s w=%.2f/%.2f"
          % (key[0], key[1], n, edge, g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7]))
