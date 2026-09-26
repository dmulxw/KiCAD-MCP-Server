"""Inventory the copper in the J1 fan-out region.

Reports, for a few candidate rip-up boxes, which nets own how much copper
there -- the size of the rip-up and the re-route order both fall out of this.
"""
import sys
from collections import defaultdict

import pcbnew

S = 1e6
B = sys.argv[1] if len(sys.argv) > 1 else "touch-panel.kicad_pcb"
b = pcbnew.LoadBoard(B)


def mm(v):
    return v / S


# --- J1 geometry -----------------------------------------------------------
j1 = None
for fp in b.GetFootprints():
    if fp.GetReference() == "J1":
        j1 = fp
        break
print("J1 bbox:",
      [round(mm(v), 3) for v in
       (j1.GetBoundingBox().GetLeft(), j1.GetBoundingBox().GetTop(),
        j1.GetBoundingBox().GetRight(), j1.GetBoundingBox().GetBottom())])
pos = j1.GetPosition()
print(f"J1 centre: ({mm(pos.x):.3f}, {mm(pos.y):.3f})")

pads = sorted(j1.Pads(), key=lambda p: p.GetPosition().x)
print(f"J1 pads: {len(pads)}  x[{mm(pads[0].GetPosition().x):.3f},"
      f"{mm(pads[-1].GetPosition().x):.3f}]"
      f" y[{min(mm(p.GetPosition().y) for p in pads):.3f},"
      f"{max(mm(p.GetPosition().y) for p in pads):.3f}]")


# --- candidate rip-up boxes ------------------------------------------------
BOXES = {
    "tight  y>242.5 x[124,150]": (124.0, 242.5, 150.0, 251.0),
    "mid    y>242.5 x[124,172]": (124.0, 242.5, 172.0, 251.0),
    "wide   y>240   x[124,172]": (124.0, 240.0, 172.0, 251.0),
    "pocket x[124,133] y[242,251]": (124.0, 242.0, 133.0, 251.0),
}

for label, (x0, y0, x1, y1) in BOXES.items():
    per_net = defaultdict(lambda: [0, 0])   # net -> [tracks, vias]
    inside = []
    for t in b.GetTracks():
        p = t.GetPosition()
        x, y = mm(p.x), mm(p.y)
        if x0 <= x <= x1 and y0 <= y <= y1:
            via = isinstance(t, pcbnew.PCB_VIA)
            per_net[t.GetNetname()][1 if via else 0] += 1
            inside.append(t)
    print(f"\n=== {label} ===  {len(inside)} item(s), {len(per_net)} net(s)")
    for net, (nt, nv) in sorted(per_net.items(),
                                key=lambda kv: -(kv[1][0] + kv[1][1])):
        print(f"   {net:<10} {nt:4d} track(s) {nv:3d} via(s)")
