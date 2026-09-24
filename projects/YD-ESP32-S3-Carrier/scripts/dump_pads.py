"""Dump every pad's absolute position, net and layer -- the routing work list."""
import pcbnew

BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
board = pcbnew.LoadBoard(BOARD)

rows = []
for fp in board.GetFootprints():
    for p in fp.Pads():
        pos = p.GetPosition()
        net = p.GetNetname()
        num = str(p.GetNumber()) or "-"
        rows.append((fp.GetReference(), num, net or "(none)",
                     pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)))

rows.sort(key=lambda r: (r[0], r[1]))
print(f"{'ref':<5} {'pad':>4} {'net':<12} {'x':>8} {'y':>8}")
for r in rows:
    print(f"{r[0]:<5} {r[1]:>4} {r[2]:<12} {r[3]:8.3f} {r[4]:8.3f}")

print("\n--- per-net pad count (excluding GND) ---")
from collections import defaultdict
nets = defaultdict(list)
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname():
            nets[p.GetNetname()].append(f"{fp.GetReference()}.{p.GetNumber()}")
for n in sorted(nets):
    print(f"  {n:<12} {len(nets[n]):>2}  {' '.join(sorted(nets[n]))}")
