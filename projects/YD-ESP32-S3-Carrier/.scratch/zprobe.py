import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM
zs = list(b.Zones())
print("zones:", len(zs), flush=True)
for n, z in enumerate(zs):
    lay = z.GetLayerSet().FmtHex()
    print(n, "rulearea" if z.GetIsRuleArea() else "fill", "layer", z.GetLayer(),
          lay, "net", z.GetNetname(), flush=True)
    try:
        poly = z.GetFilledPolysList(z.GetLayer())
        print("   outlines", poly.OutlineCount(), flush=True)
        for i in range(poly.OutlineCount()):
            print("    outline", i, "holes", poly.HoleCount(i),
                  "pts", poly.Outline(i).PointCount(), flush=True)
    except Exception as e:
        print("   ERR", e, flush=True)
