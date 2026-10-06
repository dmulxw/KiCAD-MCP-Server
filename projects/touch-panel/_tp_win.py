"""Per-cell free/via map in a window, with the blockers named."""
import importlib.util, sys, pcbnew
spec = importlib.util.spec_from_file_location("R", "_tp_route.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
NET = sys.argv[1]; x1,y1,x2,y2 = [float(v) for v in sys.argv[2].split(",")]
board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board); R.absorb(board, rt)
hw = R.WIDTHS.get(NET, R.DEFAULT_W) / 2.0
blocked, via_blocked = rt.blocked_for(NET, hw)
BL = (".", "F", "B", "#")   # (F,B) -> both free / F only / B only / neither
i0 = int(round((x1-R.OX)/R.GRID)); i1 = int(round((x2-R.OX)/R.GRID))
j0 = int(round((y1-R.OY)/R.GRID)); j1 = int(round((y2-R.OY)/R.GRID))
print("nets: " + NET)
for j in range(j0, j1+1):
    row = []
    for i in range(i0, i1+1):
        f, b = bool(blocked[0,i,j]), bool(blocked[1,i,j])
        ch = BL[(f<<1)|b]
        if not f and not b and (via_blocked[0,i,j] or via_blocked[1,i,j]):
            ch = "x"          # both free but no via
        row.append(ch)
    print("%7.2f %s" % (R.my(j), "".join(row)))
print("      " + "".join(("%-40s" % ("%.0f" % R.mx(i))) if (i-i0)%40==0 else "" for i in range(i0,i1+1)))

# name the obstacles at the specific cells asked for
for spec_xy in sys.argv[3:]:
    xx, yy = [float(v) for v in spec_xy.split(",")]
    i = int(round((xx-R.OX)/R.GRID)); j = int(round((yy-R.OY)/R.GRID))
    print("\n--- cell (%.2f,%.2f)  F=%s B=%s via=%s" % (xx, yy, blocked[0,i,j], blocked[1,i,j],
          (not via_blocked[0,i,j] and not via_blocked[1,i,j])))
    tr_r = R.CLEAR + hw; v_r = R.CLEAR + R.VIA_D/2.0
    def dist(px,py,ax,ay,bx,by):
        dx,dy = bx-ax, by-ay; L2 = dx*dx+dy*dy
        if L2 <= 1e-12: return ((px-ax)**2+(py-ay)**2)**0.5
        u = max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/L2))
        return ((px-(ax+u*dx))**2+(py-(ay+u*dy))**2)**0.5
    for (onet, layer, ax, ay, bx, by, w) in rt.frozen:
        if onet == NET: continue
        l = 0 if layer == pcbnew.F_Cu else 1
        if l != 0 and l != 1: continue
        d = dist(xx, yy, ax, ay, bx, by)
        if d <= w/2.0 + tr_r + 1e-9:
            print("   TRK %-8s L%d w=%.2f (%.3f,%.3f)->(%.3f,%.3f) d=%.3f" % (onet,l,w,ax,ay,bx,by,d))
    for (onet, vx, vy, vr) in rt.frozen_vias:
        if onet == NET: continue
        d = ((xx-vx)**2+(yy-vy)**2)**0.5
        if d <= vr + tr_r + 1e-9:
            print("   VIA %-8s (%.3f,%.3f) r=%.3f d=%.3f" % (onet,vx,vy,vr,d))
