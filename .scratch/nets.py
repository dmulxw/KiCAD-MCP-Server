import pcbnew
b = pcbnew.LoadBoard(r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb")
for ref in ("J1", "J2", "J3", "J4", "J5", "SW1", "SW2", "SW3", "SW4", "SW5", "D1", "R1", "C1", "C2", "C3", "C4"):
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        continue
    pads = sorted(fp.Pads(), key=lambda p: (str(p.GetNumber()).zfill(3)))
    print(f"{ref:<4} " + "  ".join(f"{p.GetNumber()}={p.GetNetname()}" for p in pads))
