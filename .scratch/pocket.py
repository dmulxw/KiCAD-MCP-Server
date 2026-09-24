"""Flood-fill the F.Cu GND fill from C1 pad 2 and see how far the pocket reaches."""
import pcbnew
from collections import deque

BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
b = pcbnew.LoadBoard(BOARD)
fcu = [z for z in b.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()
       and z.GetLayerSet().Contains(pcbnew.F_Cu)][0]
poly = fcu.GetFilledPolysList(pcbnew.F_Cu)

STEP = 0.10
X0, Y0, X1, Y1 = 34.0, 36.0, 54.0, 56.0          # window around C1
NX = int((X1 - X0) / STEP) + 1
NY = int((Y1 - Y0) / STEP) + 1


def inside(x, y):
    return poly.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))


mask = [[inside(X0 + i * STEP, Y0 + j * STEP) for i in range(NX)] for j in range(NY)]


def walk(si, sj):
    """Flood fill the copper component containing cell (si,sj). Returns its cells."""
    if not mask[sj][si]:
        return set()
    seen, q = {(si, sj)}, deque([(si, sj)])
    while q:
        i, j = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if 0 <= ni < NX and 0 <= nj < NY and mask[nj][ni] and (ni, nj) not in seen:
                seen.add((ni, nj))
                q.append((ni, nj))
    return seen


# seed: just right of C1 pad 2, inside the keep-out ring the fill leaves round the pad
seed = None
for r in [0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6]:
    si = int((44.0 + r - X0) / STEP)
    sj = int((42.5 - Y0) / STEP)
    if mask[sj][si]:
        seed = (si, sj)
        print(f"seed at ({44.0+r:.2f},{42.5:.2f})")
        break
if seed is None:
    raise SystemExit("no filled copper immediately around C1 pad 2")

cells = walk(*seed)
xs = [X0 + i * STEP for i, _ in cells]
ys = [Y0 + j * STEP for _, j in cells]
print(f"pocket: {len(cells)} cells ({len(cells)*STEP*STEP:.2f} mm^2), "
      f"bbox x {min(xs):.2f}..{max(xs):.2f}  y {min(ys):.2f}..{max(ys):.2f}")

# is it the same component as the bulk of the plane?
far = walk(int((36.0 - X0) / STEP), int((55.0 - Y0) / STEP))
print(f"main plane component reached from (36,55): {len(far)} cells")
print("SAME component -- pocket is live copper" if cells == far
      else "SEPARATE -- pocket is an island reachable only through C1.2")

# does the main plane come near? nearest distance from pocket to the rest
if cells != far:
    near = min(((X0 + i * STEP) - (X0 + k * STEP)) ** 2 + ((Y0 + j * STEP) - (Y0 + l * STEP)) ** 2
               for i, j in cells for k, l in list(far)[:4000]) ** 0.5
    print(f"nearest approach between pocket and main plane: {near:.2f} mm")
