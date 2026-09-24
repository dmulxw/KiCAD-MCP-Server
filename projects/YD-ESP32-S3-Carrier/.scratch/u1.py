import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM
f = b.FindFootprintByReference("U1")
print("U1", f.GetFPID().GetLibItemName(), flush=True)
A = {getattr(pcbnew, n): n for n in dir(pcbnew) if n.startswith("PAD_ATTRIB_")}
S = {getattr(pcbnew, n): n for n in dir(pcbnew) if n.startswith("PAD_SHAPE_")}
for p in f.Pads():
    pos = p.GetPosition()
    n = str(p.GetNumber())
    print(f"  pad {n!r:>5} @({mm(pos.x):7.3f},{mm(pos.y):7.3f})"
          f" size {mm(p.GetSize().x):.2f}x{mm(p.GetSize().y):.2f}"
          f" drill {mm(p.GetDrillSize().x):.2f}x{mm(p.GetDrillSize().y):.2f}"
          f" {A.get(p.GetAttribute(),'?'):<22} {S.get(p.GetShape(),'?'):<14}"
          f" net={p.GetNetname() or '-'}", flush=True)
