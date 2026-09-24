"""Real pad positions and body boxes for the v2 power section, so
verify_geometry.py's placement assertions are written against measured numbers
rather than against the plan's estimates."""
import math

import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}


def mm(v):
    return pcbnew.ToMM(v)


def pad(ref, num, idx=0):
    hits = [p for p in fps[ref].Pads() if str(p.GetNumber()) == str(num)]
    p = hits[idx]
    pos = p.GetPosition()
    return mm(pos.x), mm(pos.y)


CHARGE = ["U1", "C5", "C6", "R2", "R3", "D3"]
BOOST = ["L1", "U2", "D2", "C7", "C8", "R4", "R5"]

for name, refs in (("charge", CHARGE), ("boost", BOOST)):
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    print(f"--- {name} ---")
    for ref in refs:
        b = fps[ref].GetBoundingBox(False, False)     # body/courtyard, no text
        bx = (mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom()))
        x0, y0 = min(x0, bx[0]), min(y0, bx[1])
        x1, y1 = max(x1, bx[2]), max(y1, bx[3])
        nets = {str(p.GetNumber()): p.GetNetname() for p in fps[ref].Pads()}
        print(f"  {ref:<3} x {bx[0]:7.2f}..{bx[2]:<7.2f} y {bx[1]:7.2f}..{bx[3]:<7.2f}  {nets}")
    print(f"  union: x {x0:.2f}..{x1:.2f}  y {y0:.2f}..{y1:.2f}")

print("\n--- SW_NODE loop: U2.SW - L1 - D2.A ---")
sw = pad("U2", 1)
print(f"  U2.SW  {sw}")
for n in ("1", "2"):
    print(f"  L1.{n}  {pad('L1', n)}   dist U2.SW = "
          f"{math.dist(sw, pad('L1', n)):.2f}")
print(f"  D2.A(2) {pad('D2', 2)}   dist U2.SW = {math.dist(sw, pad('D2', 2)):.2f}")
l1 = pad("L1", 2)
print(f"  L1.2 -> D2.A = {math.dist(l1, pad('D2', 2)):.2f}")

print("\n--- D2.K(1) is on +5V? ---")
print("  D2.1 net:", [p.GetNetname() for p in fps["D2"].Pads() if str(p.GetNumber()) == "1"])
print("  D2.2 net:", [p.GetNetname() for p in fps["D2"].Pads() if str(p.GetNumber()) == "2"])
