"""Which spot on the panel can reach all thirty-one strip lines most cheaply?

The four shift registers have to drive every ROW and CSEL net, and those nets
are spread over the whole keyboard.  Picking a placement by eye is guesswork, so
measure it: sample the copper of each net, then for every millimetre of the
board compute the distance to the nearest copper of every net.  The cost of a
placement is how far the worst net is (max) and how much copper it would take in
total (sum).  Anything but the front copper layer is reachable through a via,
so plain Euclidean distance is the right proxy.

  python _tp_reach.py [--step 1.0]
"""
import re
import sys

import numpy as np
import pcbnew

PCB = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
STEP = 1.0
if "--step" in sys.argv:
    STEP = float(sys.argv[sys.argv.index("--step") + 1])

WANT = re.compile(r"^(ROW\d+|CSEL\d+)$")

b = pcbnew.LoadBoard(PCB)

# --- board frame ----------------------------------------------------------
box = b.GetBoardEdgesBoundingBox()
X0, Y0 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
W, H = pcbnew.ToMM(box.GetWidth()), pcbnew.ToMM(box.GetHeight())
nx, ny = int(W / STEP), int(H / STEP)
gx = X0 + (np.arange(nx) + 0.5) * STEP
gy = Y0 + (np.arange(ny) + 0.5) * STEP
GX, GY = np.meshgrid(gx, gy)

# --- sample the copper of each net ----------------------------------------
code_of = {}
for code, net in b.GetNetInfo().NetsByNetcode().items():
    nm = net.GetNetname().lstrip("/")
    if WANT.match(nm):
        code_of[nm] = code

pts = {nm: [] for nm in code_of}
for t in b.GetTracks():
    nm = t.GetNetname().lstrip("/")
    if nm not in pts:
        continue
    s, e = t.GetStart(), t.GetEnd()
    ax, ay = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
    bx, by = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
    n = max(2, min(40, int(np.hypot(bx - ax, by - ay) / 0.5) + 1))
    for k in range(n):
        f = k / (n - 1.0)
        pts[nm].append((ax + (bx - ax) * f, ay + (by - ay) * f))
for fp in b.GetFootprints():
    for p in fp.Pads():
        nm = p.GetNetname().lstrip("/")
        if nm in pts:
            q = p.GetPosition()
            pts[nm].append((pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)))

names = sorted(pts)
print("%d net(s), %d sample point(s) total"
      % (len(names), sum(len(v) for v in pts.values())))

# --- distance to each net, everywhere -------------------------------------
dist = np.empty((len(names), ny, nx), dtype=np.float32)
for i, nm in enumerate(names):
    a = np.asarray(pts[nm], dtype=np.float32)
    d = np.full((ny, nx), 1e9, dtype=np.float32)
    for k in range(0, len(a), 256):
        c = a[k:k + 256]
        dd = np.sqrt((GX[..., None] - c[:, 0]) ** 2
                     + (GY[..., None] - c[:, 1]) ** 2)
        np.minimum(d, dd.min(axis=2), out=d)
    dist[i] = d

worst = dist.max(axis=0)
total = dist.sum(axis=0)

# --- the board edge is a wall ---------------------------------------------
edge = np.zeros((ny, nx), dtype=bool)
for o in b.GetDrawings():
    if o.GetLayer() != pcbnew.Edge_Cuts:
        continue
    r = o.GetBoundingBox()
    ax, ay = pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY())
    bx = ax + pcbnew.ToMM(r.GetWidth())
    by = ay + pcbnew.ToMM(r.GetHeight())
    m = 1.0
    ix0 = max(0, int((ax - X0 - m) / STEP))
    ix1 = min(nx, int((bx - X0 + m) / STEP) + 1)
    iy0 = max(0, int((ay - Y0 - m) / STEP))
    iy1 = min(ny, int((by - Y0 + m) / STEP) + 1)
    edge[iy0:iy1, ix0:ix1] = True

# --- footprint keep-clear (the chips go on the back, so front parts are no
# obstacle for placement, only for the vias that must reach the front) -----
print("\n=== best placement by worst-net distance (front copper)")
order = np.argsort(worst, axis=None)
shown = 0
seen = []
for idx in order:
    iy, ix = divmod(int(idx), nx)
    if edge[iy, ix] or worst[iy, ix] > 1e8:
        continue
    px, py = gx[ix], gy[iy]
    if any(abs(px - a) < 12 and abs(py - b2) < 12 for a, b2 in seen):
        continue
    seen.append((px, py))
    print("   (%7.2f, %7.2f)  worst net %6.2f mm   sum %8.1f mm"
          % (px, py, worst[iy, ix], total[iy, ix]))
    shown += 1
    if shown >= 8:
        break

print("\n=== best placement by total distance")
order = np.argsort(total, axis=None)
shown = 0
seen = []
for idx in order:
    iy, ix = divmod(int(idx), nx)
    if edge[iy, ix] or worst[iy, ix] > 1e8:
        continue
    px, py = gx[ix], gy[iy]
    if any(abs(px - a) < 12 and abs(py - b2) < 12 for a, b2 in seen):
        continue
    seen.append((px, py))
    print("   (%7.2f, %7.2f)  worst net %6.2f mm   sum %8.1f mm"
          % (px, py, worst[iy, ix], total[iy, ix]))
    shown += 1
    if shown >= 8:
        break

# --- and the specific areas that looked empty ------------------------------
print("\n=== named candidates: distance from the area to each net")
CAND = {
    "back strip, low  (94.95, 235)": (94.95, 235.0),
    "back strip, high (94.95, 205)": (94.95, 205.0),
    "right strip      (172.0, 140)": (172.0, 140.0),
    "right strip low  (172.0, 175)": (172.0, 175.0),
    "above J1         (135.0, 235)": (135.0, 235.0),
    "board centre     (135.0, 175)": (135.0, 175.0),
}
for label, (px, py) in CAND.items():
    iy = min(ny - 1, max(0, int((py - Y0) / STEP)))
    ix = min(nx - 1, max(0, int((px - X0) / STEP)))
    col = dist[:, iy, ix]
    far = sorted(zip(col.tolist(), names))[-5:]
    print("   %-30s worst %6.2f  sum %7.1f   farthest: %s"
          % (label, col.max(), col.sum(),
             " ".join("%s(%.1f)" % (n, d) for d, n in far)))
