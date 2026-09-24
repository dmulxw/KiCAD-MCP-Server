"""Which pad sits at (45.275, 38.115), and where is the rest of +5V?

route.py reported "+5V: cannot reach pad (45.275, 38.115)" and then still
printed the net as OK, which means the A* gave up on one pad while connecting
the others.  That reads as routed on the console and as an open net at DRC.
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)


def mm(v):
    return pcbnew.ToMM(v)


print("--- every +5V pad ---")
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname() != "+5V":
            continue
        pos = p.GetPosition()
        print(f"  {fp.GetReference():<4} pad {str(p.GetNumber()):<3} "
              f"({mm(pos.x):7.3f}, {mm(pos.y):7.3f})  "
              f"size {mm(p.GetSize().x):.2f}x{mm(p.GetSize().y):.2f}  "
              f"{p.GetShape()}  layers={p.GetLayerSet().FmtHex()}")

print("\n--- footprints near (45.275, 38.115) ---")
for fp in board.GetFootprints():
    b = fp.GetBoundingBox(False, False)
    if (mm(b.GetLeft()) <= 45.275 <= mm(b.GetRight())
            and mm(b.GetTop()) <= 38.115 <= mm(b.GetBottom())):
        print(f"  {fp.GetReference():<4} {fp.GetFPID().GetLibItemName()}  "
              f"x {mm(b.GetLeft()):.2f}..{mm(b.GetRight()):.2f} "
              f"y {mm(b.GetTop()):.2f}..{mm(b.GetBottom()):.2f}")
        for p in fp.Pads():
            pos = p.GetPosition()
            print(f"        pad {str(p.GetNumber()):<3} "
                  f"({mm(pos.x):7.3f}, {mm(pos.y):7.3f})  net={p.GetNetname()}")
