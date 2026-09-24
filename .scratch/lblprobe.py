import pcbnew
B = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
board = pcbnew.LoadBoard(B)
def bb(o):
    b = o.GetBoundingBox()
    return tuple(round(pcbnew.ToMM(v), 2) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
want = {"+5V", "GND", "BAT 5V", "PWR SW", "AUDIO", "ES8311"}
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.F_SilkS and d.GetClass() == "PCB_TEXT" and d.GetText() in want:
        p = d.GetPosition()
        print(f"{d.GetText()!r:<9} anchor=({pcbnew.ToMM(p.x):6.2f},{pcbnew.ToMM(p.y):6.2f}) "
              f"ang={d.GetTextAngleDegrees():5.0f}  bbox={bb(d)}")
print()
for ref, num in (("J5", "1"), ("J5", "2"), ("J3", "10")):
    for p in board.FindFootprintByReference(ref).Pads():
        if str(p.GetNumber()) == num:
            q = p.GetPosition()
            print(f"{ref}.{num} pad at ({pcbnew.ToMM(q.x):6.2f},{pcbnew.ToMM(q.y):6.2f})")
