"""Full-board peel: how many connected components does the F.Cu GND fill have,
and where do the stitching vias sit relative to them?"""
import pcbnew
from collections import deque

BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
b = pcbnew.LoadBoard(BOARD)
fcu = [z for z in b.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()
       and z.GetLayerSet().Contains(pcbnew.F_Cu)][0]
poly = fcu.GetFilledPolysList(pcbnew.F_Cu)

STEP = 0.20
X0, Y0, X1, Y1 = 0.0, 0.0, 74.0, 88.0
NX = int((X1 - X0) / STEP) + 1
NY = int((Y1 - Y0) / STEP) + 1
mask = [[poly.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(X0 + i * STEP),
                                       pcbnew.FromMM(Y0 + j * STEP)))
         for i in range(NX)] for j in range(NY)]
print(f"grid {NX}x{NY} at {STEP} mm, seed area {STEP*STEP:.3f} mm^2")

seen_global = set()
comps = []
for j in range(NY):
    for i in range(NX):
        if not mask[j][i] or (i, j) in seen_global:
            continue
        seen, q = {(i, j)}, deque([(i, j)])
        seen_global.add((i, j))
        while q:
            a, c = q.popleft()
            for da, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                na, nc = a + da, c + dc
                if 0 <= na < NX and 0 <= nc < NY and mask[nc][na] and (na, nc) not in seen:
                    seen.add((na, nc)); seen_global.add((na, nc)); q.append((na, nc))
        xs = [X0 + a * STEP for a, _ in seen]; ys = [Y0 + c * STEP for _, c in seen]
        comps.append((len(seen), (min(xs), min(ys), max(xs), max(ys)), seen))

comps.sort(reverse=True, key=lambda t: t[0])
print(f"\n{len(comps)} connected component(s) of F.Cu fill:")
for k, (n, bb, _) in enumerate(comps[:8]):
    print(f"  #{k}  {n*STEP*STEP:8.1f} mm^2   bbox ({bb[0]:5.1f},{bb[1]:5.1f})-({bb[2]:5.1f},{bb[3]:5.1f})")

def comp_of(x, y):
    i, j = int(round((x - X0) / STEP)), int(round((y - Y0) / STEP))
    for k, (_, _, cells) in enumerate(comps):
        if (i, j) in cells:
            return k
    return None

print("\nGND stitching vias -> which component (None = via is in a hole in the fill):")
tally = {}
for t in b.GetTracks():
    if t.GetClass() != "PCB_VIA" or t.GetNetname() != "GND":
        continue
    x, y = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)
    k = comp_of(x, y)
    tally.setdefault(k, []).append((round(x, 1), round(y, 1)))
for k in sorted(tally, key=lambda v: (v is None, v)):
    print(f"  component #{k}: {len(tally[k])} via(s)")

print("\nGND pads -> component:")
ptally = {}
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname() != "GND":
            continue
        x, y = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        ptally.setdefault(comp_of(x, y), []).append(
            f"{fp.GetReference()}.{p.GetNumber()}")
for k in sorted(ptally, key=lambda v: (v is None, v)):
    print(f"  component #{k}: {', '.join(sorted(ptally[k]))}")
