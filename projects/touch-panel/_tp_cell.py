"""Which obstacles block one specific grid cell, per layer?"""
import importlib.util, sys, numpy as np, pcbnew
spec = importlib.util.spec_from_file_location("R", "_tp_route.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
NET = sys.argv[1]
xs = [float(v) for v in sys.argv[2].split(",")]
ys = [float(v) for v in sys.argv[3].split(",")]
board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board); R.absorb(board, rt)
w = R.WIDTHS.get(NET, R.DEFAULT_W); hw = w/2.0
blocked, via_blocked = rt.blocked_for(NET, hw)
tr_r = R.CLEAR + hw
v_r = R.CLEAR + R.VIA_D/2.0

def test(i, j):
    print("\n--- cell (%.2f, %.2f) i=%d j=%d" % (R.mx(i), R.my(j), i, j))
    for l in (0, 1):
        print("   layer %d: trace_blocked=%s via_blocked=%s"
              % (l, blocked[l,i,j], via_blocked[l,i,j]))
    for other, kind, a, layers in rt.shapes:
        if other == NET or 0 not in layers and 1 not in layers:
            pass
        for l in layers:
            m = np.zeros((R.NL, R.NX, R.NY), dtype=bool)
            v = np.zeros_like(m)
            if kind == "circle":
                R.raster_circle(m, l, a[0], a[1], a[2] + tr_r)
                R.raster_circle(v, l, a[0], a[1], a[2] + v_r)
            else:
                x0,y0,x1,y1 = a
                R.raster_rect(m, l, x0, y0, x1, y1, tr_r)
                R.raster_rect(v, l, x0, y0, x1, y1, v_r)
            if m[l,i,j] or v[l,i,j]:
                print("   PAD  %-9s L%d %s %s" % (other, l,
                      "trace" if m[l,i,j] else "     ",
                      "via" if v[l,i,j] else ""))
    for (onet, layer, x1,y1,x2,y2,ww) in rt.frozen:
        if onet == NET: continue
        m = np.zeros((R.NL,R.NX,R.NY), dtype=bool); v = np.zeros_like(m)
        R.raster_seg(m, layer, x1,y1,x2,y2, ww/2.0 + tr_r)
        R.raster_seg(v, layer, x1,y1,x2,y2, ww/2.0 + v_r)
        if m[layer,i,j] or v[layer,i,j]:
            print("   TRK  %-9s L%d w=%.2f (%.3f,%.3f)->(%.3f,%.3f) %s%s"
                  % (onet, layer, ww, x1,y1,x2,y2,
                     "trace" if m[layer,i,j] else "", " via" if v[layer,i,j] else ""))
    for (vnet, vx, vy) in rt.frozen_vias:
        if vnet == NET: continue
        for l in (0,1):
            m = np.zeros((R.NL,R.NX,R.NY), dtype=bool); v = np.zeros_like(m)
            R.raster_circle(m, l, vx, vy, R.VIA_D/2.0 + tr_r)
            R.raster_circle(v, l, vx, vy, R.VIA_D/2.0 + v_r)
            if m[l,i,j] or v[l,i,j]:
                print("   VIA  %-9s L%d (%.3f,%.3f)" % (vnet, l, vx, vy))

for y in ys:
    for x in xs:
        i = int(round((x - R.OX)/R.GRID)); j = int(round((y - R.OY)/R.GRID))
        test(i, j)
