"""For each copper layer, which y values allow a horizontal 0.20 trace to run
clean across the wall band?

The wall is x ~= 100.0..101.9.  A net gets from the 595 outputs to the east
network only if there is a y where a horizontal trace clears every obstacle on
ONE layer for the full width of the band.  So sweep y and record the run.

  python _tp_door2.py [X1] [X2] [W]
"""
import sys, pcbnew
BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
X1 = float(sys.argv[1]) if len(sys.argv) > 1 else 98.60
X2 = float(sys.argv[2]) if len(sys.argv) > 2 else 101.80
W = float(sys.argv[3]) if len(sys.argv) > 3 else 0.20
CLEAR, HW = 0.16, W / 2.0

board = pcbnew.LoadBoard(BOARD)

# obstacles per layer: (x1,y1,x2,y2,radius) where radius already includes clearance
obs = {0: [], 1: []}
for t in board.GetTracks():
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = TO(a.x), TO(a.y), TO(b.x), TO(b.y)
    if isinstance(t, pcbnew.PCB_VIA):
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2.0 + CLEAR + HW
        for l in (0, 1):
            obs[l].append((ax, ay, ax, ay, r))
        continue
    l = t.GetLayer()
    if l not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    li = 0 if l == pcbnew.F_Cu else 1
    obs[li].append((ax, ay, bx, by, TO(t.GetWidth()) / 2.0 + CLEAR + HW))
for f in board.GetFootprints():
    for p in f.Pads():
        o = p.GetPosition()
        px, py = TO(o.x), TO(o.y)
        pb = p.GetBoundingBox()
        hw = max(TO(pb.GetWidth()), TO(pb.GetHeight())) / 2.0
        if p.GetDrillSize().x:
            hw = max(hw, TO(p.GetDrillSize().x) / 2.0)
        r = hw + CLEAR + HW
        on = [0, 1] if (p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH) else (
            [0] if p.IsOnLayer(pcbnew.F_Cu) else [1])
        for l in on:
            obs[l].append((px, py, px, py, r))

for li in (0, 1):
    name = board.GetLayerName(pcbnew.F_Cu if li == 0 else pcbnew.B_Cu)
    runs, y = [], 100.0
    while y <= 250.0:
        ax, ay = X1, y
        blocked = None
        for (px, py, qx, qy, r) in obs[li]:
            # does this obstacle come within r of the horizontal segment?
            if min(py, qy) - r > y or max(py, qy) + r < y:
                continue
            if qx == px and qy == py:          # point obstacle
                d = ((max(X1, min(px, X2)) - px) ** 2 + (y - py) ** 2) ** 0.5
                if min(px, X1) > X2 or max(px, X2) < X1:
                    pass
            else:
                lo, hi = min(px, qx), max(px, qx)
                if hi < X1 or lo > X2:
                    continue
                # vertical distance to the segment, clamped to the x window
                cx = max(lo, min(hi, (X1 + X2) / 2.0))
                dx, dy = qx - px, qy - py
                L2 = dx * dx + dy * dy
                u = ((cx - px) * dx + (y - py) * dy) / L2 if L2 else 0.0
                u = max(0.0, min(1.0, u))
                d = ((cx - (px + u * dx)) ** 2 + (y - (py + u * dy)) ** 2) ** 0.5
                if d > r:
                    continue
            if blocked is None or True:
                blocked = True
                break
        (runs.append([y, y]) if not blocked and runs and runs[-1][1] == round(y - 0.2, 1)
         else runs.append([y, y])) if not blocked else None
        y = round(y + 0.2, 1)
    # merge
    merged = []
    for (a, b) in runs:
        merged.append([a, b])
    print("%s: y-runs where a %.2f trace crosses x %.2f..%.2f with no obstacle "
          "(within board y 100..250):" % (name, W, X1, X2))
    if not merged:
        print("   NONE")
    else:
        for (a, b) in merged:
            print("   y %7.2f .. %7.2f   (%.2f mm)" % (a, b, b - a))
