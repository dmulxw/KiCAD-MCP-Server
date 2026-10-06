"""Coarse occupancy map of the carrier: what is where, and where is free."""
import sys
import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
TO = pcbnew.ToMM
b = pcbnew.LoadBoard(BOARD)

X0, Y0, X1, Y1 = 0.0, 0.0, 100.0, 74.0
STEP = 1.0
NX = int((X1 - X0) / STEP)
NY = int((Y1 - Y0) / STEP)
g = [[" "] * NX for _ in range(NY)]

def put(x0, y0, x1, y1, ch):
    for j in range(max(0, int((y0 - Y0) / STEP)), min(NY, int((y1 - Y0) / STEP) + 1)):
        for i in range(max(0, int((x0 - X0) / STEP)), min(NX, int((x1 - X0) / STEP) + 1)):
            if g[j][i] == " " or ch.isalpha():
                g[j][i] = ch

# courtyards first (light), then pads (heavy)
for f in b.GetFootprints():
    cb = f.GetCourtyard(pcbnew.F_CrtYd)
    if cb.GetWidth() > 0:
        put(TO(cb.GetLeft()), TO(cb.GetTop()), TO(cb.GetRight()), TO(cb.GetBottom()), ".")
    for p in f.Pads():
        pb = p.GetBoundingBox()
        put(TO(pb.GetLeft()), TO(pb.GetTop()), TO(pb.GetRight()), TO(pb.GetBottom()), "#")

# mounting holes explicitly
for f in b.GetFootprints():
    if "MountingHole" in str(f.GetFPID().GetLibItemName()):
        p = f.GetPosition()
        put(TO(p.x) - 2, TO(p.y) - 2, TO(p.x) + 2, TO(p.y) + 2, "O")

print("carrier occupancy, 1 mm cells.  #=pad  .=courtyard only  O=mounting hole")
print("    " + "".join(str((int(X0) + i) % 10) for i in range(NX)))
for j in range(NY):
    print("%3d " % (int(Y0) + j) + "".join(g[j]))

print("\n=== free runs on the bottom strip, y 62..74 ===")
for j in range(62, 74):
    row = g[j - int(Y0)]
    out, k = [], 0
    while k < NX:
        if row[k] != " ":
            k += 1
            continue
        s = k
        while k < NX and row[k] == " ":
            k += 1
        if k - s >= 3:
            out.append("%d..%d(%d)" % (s, k, k - s))
    print("  y=%2d  %s" % (j, "  ".join(out) if out else "-"))

print("\n=== free runs in the right column, x 40..100 ===")
for i in range(40, 100):
    col = [g[j][i] for j in range(NY)]
    out, k = 0, 0
    runs, s = [], None
    while k < NY:
        if col[k] != " ":
            if s is not None:
                if k - s >= 3: runs.append("%d..%d" % (s, k))
                s = None
            k += 1
            continue
        if s is None: s = k
        k += 1
    if s is not None and NY - s >= 3: runs.append("%d..%d" % (s, NY))
    if runs:
        print("  x=%2d  %s" % (i, "  ".join(runs)))
