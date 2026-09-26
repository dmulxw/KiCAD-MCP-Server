"""Dump J1's pad layout and the copper immediately around pads 4 and 6."""
import sys
from collections import defaultdict

import pcbnew

S = 1e6
B = sys.argv[1] if len(sys.argv) > 1 else "touch-panel.kicad_pcb"
b = pcbnew.LoadBoard(B)
mm = lambda v: v / S

j1 = next(fp for fp in b.GetFootprints() if fp.GetReference() == "J1")
pads = list(j1.Pads())
print(f"J1 has {len(pads)} pads")
rows = defaultdict(list)
for p in pads:
    pos = p.GetPosition()
    sz = p.GetSize()
    bb = p.GetBoundingBox()
    rows[round(mm(pos.y), 2)].append(
        (p.GetNumber(), round(mm(pos.x), 3), round(mm(sz.x), 3), round(mm(sz.y), 3),
         p.GetNetname()))
for y in sorted(rows):
    r = sorted(rows[y], key=lambda t: t[1])
    print(f"\nrow y={y}: {len(r)} pad(s), x[{r[0][1]:.3f} -> {r[-1][1]:.3f}]"
          f"  size {r[0][2]}x{r[0][3]}")
    print("   " + "  ".join(f"{n}@{x}" for n, x, _, _, _ in r))
    print("   " + "  ".join(f"{net}" for _, _, _, _, net in r))

# pitch within the most populated row
y = max(rows, key=lambda k: len(rows[k]))
r = sorted(rows[y], key=lambda t: t[1])
d = [round(r[i + 1][1] - r[i][1], 4) for i in range(len(r) - 1)]
print(f"\npitch histogram on y={y}: "
      f"{sorted(set(d))}")

# --- what is around J1 pads 4 and 6 ---------------------------------------
print("\n--- copper within 3mm of J1 pad 4 and pad 6 ---")
for num in ("4", "6"):
    pad = next(p for p in pads if p.GetNumber() == num)
    pp = pad.GetPosition()
    px, py = mm(pp.x), mm(pp.y)
    print(f"\npad {num} {pad.GetNetname()} at ({px:.3f},{py:.3f}) "
          f"size {mm(pad.GetSize().x):.3f}x{mm(pad.GetSize().y):.3f}")
    near = []
    for t in b.GetTracks():
        p = t.GetPosition()
        dx, dy = mm(p.x) - px, mm(p.y) - py
        if dx * dx + dy * dy < 9.0:
            via = isinstance(t, pcbnew.PCB_VIA)
            lay = "VIA" if via else b.GetLayerName(t.GetLayer())
            near.append((round(dx, 2), round(dy, 2), lay, t.GetNetname(),
                         "via" if via else "trk"))
    for dx, dy, lay, net, kind in sorted(near, key=lambda t: t[0] ** 2 + t[1] ** 2):
        print(f"   ({px+dx:8.3f},{py+dy:8.3f})  {lay:<6} {net:<8} {kind}")
