import pcbnew
B = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
board = pcbnew.LoadBoard(B)
print(f"zones on board: {len(board.Zones())}")
for i, z in enumerate(board.Zones()):
    kind = "rule area" if z.GetIsRuleArea() else f"pour net={z.GetNetname()}"
    layers = [pcbnew.LayerName(l) for l in z.GetLayerSet().Seq()]
    print(f"\nzone {i}: {kind}  layers={layers}")
    for l in z.GetLayerSet().Seq():
        polys = z.GetFilledPolysList(l)
        n = polys.OutlineCount()
        area = 0.0
        for k in range(n):
            area += abs(polys.Outline(k).Area())
        print(f"   layer {pcbnew.LayerName(l):<6} filled outlines={n:<3} "
              f"area={pcbnew.ToMM(pcbnew.ToMM(area)):10.1f} mm2")
