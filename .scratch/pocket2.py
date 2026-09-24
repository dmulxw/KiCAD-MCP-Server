import math, pcbnew
BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
b = pcbnew.LoadBoard(BOARD)
X0, Y0, X1, Y1 = 41.30, 42.30, 54.00, 56.00
print(f"pocket box x {X0}..{X1}  y {Y0}..{Y1}")
print("\n-- GND vias inside the pocket --")
n = 0
for t in b.GetTracks():
    if t.GetClass() != "PCB_VIA" or t.GetNetname() != "GND":
        continue
    x, y = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)
    if X0 <= x <= X1 and Y0 <= y <= Y1:
        print(f"   via ({x:.2f},{y:.2f})"); n += 1
print(f"   {n} GND via(s) inside")
print("\n-- GND pads inside the pocket --")
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname() != "GND":
            continue
        x, y = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        if X0 <= x <= X1 and Y0 <= y <= Y1:
            print(f"   {fp.GetReference()}.{p.GetNumber():<3} ({x:.2f},{y:.2f})")
print("\n-- GND vias anywhere in the lower half (y>50), to see the lattice --")
vs = sorted((pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y))
            for t in b.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND")
print(f"   {len(vs)} total; y range {min(v[1] for v in vs):.1f}..{max(v[1] for v in vs):.1f}")
print(f"   x range {min(v[0] for v in vs):.1f}..{max(v[0] for v in vs):.1f}")
print(f"   vias with y>50: {[f'({x:.1f},{y:.1f})' for x, y in vs if y > 50][:20]}")
