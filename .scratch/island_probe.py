import pcbnew
BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
b = pcbnew.LoadBoard(BOARD)
print("ISLAND_REMOVAL_MODE_*:",
      [(n, getattr(pcbnew, n)) for n in dir(pcbnew) if "ISLAND" in n.upper()])
for z in b.Zones():
    if z.GetIsRuleArea():
        continue
    n = sum(1 for l in (pcbnew.F_Cu, pcbnew.B_Cu)
            if z.GetLayerSet().Contains(l) and z.GetFilledPolysList(l).OutlineCount())
    print(f"zone {z.GetNetname()} layer={z.GetLayer()} island_mode="
          f"{z.GetIslandRemovalMode()} outlines={n}")
