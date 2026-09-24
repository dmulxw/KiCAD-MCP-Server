"""Bounding boxes of everything already on the board -- so place.py can dodge them."""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
board = pcbnew.LoadBoard(BOARD)

for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
    bb = fp.GetBoundingBox(False, False)
    x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
    print(f"{fp.GetReference():<5} ({x0:7.3f},{y0:7.3f})-({x1:7.3f},{y1:7.3f})"
          f"   {x1-x0:6.3f} x {y1-y0:6.3f}   {str(fp.GetFPID().GetLibItemName())}")
