"""Name every obstacle blocking one grid cell (trace and via), for a list of cells."""
import importlib.util, sys, pcbnew
spec = importlib.util.spec_from_file_location("R", "_tp_route.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
NET = sys.argv[1]
board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board); R.absorb(board, rt)
hw = R.WIDTHS.get(NET, R.DEFAULT_W) / 2.0
blocked, via_blocked = rt.blocked_for(NET, hw)
tr_r = R.CLEAR + hw; v_r = R.CLEAR + R.VIA_D / 2.0
print("frozen: %d tracks, %d vias   tr_r=%.3f v_r=%.3f" % (len(rt.frozen), len(rt.frozen_vias), tr_r, v_r))

def dist(px, py, ax, ay, bx, by):
    dx, dy = bx-ax, by-ay; L2 = dx*dx+dy*dy
    if L2 <= 1e-12: return ((px-ax)**2+(py-ay)**2)**0.5
    u = max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/L2))
    return ((px-(ax+u*dx))**2+(py-(ay+u*dy))**2)**0.5

for xy in sys.argv[2:]:
    xx, yy = [float(v) for v in xy.split(",")]
    i = int(round((xx-R.OX)/R.GRID)); j = int(round((yy-R.OY)/R.GRID))
    print("\n=== cell (%.2f,%.2f)  Fblock=%-5s Bblock=%-5s viaF=%-5s viaB=%s"
          % (xx, yy, blocked[0,i,j], blocked[1,i,j], via_blocked[0,i,j], via_blocked[1,i,j]))
    for ent in rt.frozen:
        onet, layer, ax, ay, bx, by, w = ent[:7]
        if onet == NET: continue
        l = int(layer) if int(layer) in (0, 1) else (
            0 if layer == pcbnew.F_Cu else (1 if layer == pcbnew.B_Cu else -1))
        if l < 0: continue
        d = dist(xx, yy, ax, ay, bx, by)
        if d <= w/2.0 + tr_r + 1e-9:
            print("   TRACE L%d %-9s w=%.2f (%.3f,%.3f)->(%.3f,%.3f) d=%.3f need=%.3f"
                  % (l, onet, w, ax, ay, bx, by, d, w/2.0+tr_r))
    for ent in rt.frozen_vias:
        onet, vx, vy = ent[0], ent[1], ent[2]
        vr = ent[3] if len(ent) > 3 else R.VIA_D/2.0
        if onet == NET: continue
        d = ((xx-vx)**2+(yy-vy)**2)**0.5
        if d <= vr + v_r + 1e-9:
            print("   VIA       %-9s (%.3f,%.3f) r=%.3f d=%.3f" % (onet, vx, vy, vr, d))
