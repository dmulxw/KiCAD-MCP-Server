"""Measured body and pad boxes for the parts whose silk needs moving."""
import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM
for ref in ("C5", "C6", "C8", "R3", "R4", "R5", "SW1", "SW3"):
    f = b.FindFootprintByReference(ref)
    bb = f.GetBoundingBox(False, False)
    cu = f.GetBoundingBox(True, True)
    print(f"{ref:<4} body x {mm(bb.GetLeft()):7.2f}..{mm(bb.GetRight()):<7.2f}"
          f" y {mm(bb.GetTop()):7.2f}..{mm(bb.GetBottom()):<7.2f}"
          f" | cu x {mm(cu.GetLeft()):7.2f}..{mm(cu.GetRight()):<7.2f}"
          f" y {mm(cu.GetTop()):7.2f}..{mm(cu.GetBottom()):<7.2f}", flush=True)
    for p in f.Pads():
        pos, sz = p.GetPosition(), p.GetSize()
        print(f"      pad {str(p.GetNumber()):<3} @({mm(pos.x):7.2f},{mm(pos.y):7.2f})"
              f" {mm(sz.x):.2f}x{mm(sz.y):.2f}", flush=True)
    # silk graphics of the footprint
    for g in f.GraphicalItems():
        if str(g.GetLayerName()) == "F.Silkscreen":
            gb = g.GetBoundingBox()
            print(f"      silk {g.GetClass()} x {mm(gb.GetLeft()):7.2f}..{mm(gb.GetRight()):<7.2f}"
                  f" y {mm(gb.GetTop()):7.2f}..{mm(gb.GetBottom()):<7.2f}", flush=True)
