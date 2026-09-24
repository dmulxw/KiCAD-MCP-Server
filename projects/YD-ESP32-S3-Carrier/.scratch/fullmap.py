import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
zs = {zz.GetLayer(): zz for zz in b.Zones() if not zz.GetIsRuleArea()}
# island removal off, refill, so the true poured area is visible
for zz in b.Zones():
    if not zz.GetIsRuleArea():
        zz.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())

def mark(x, y):
    s = ""
    for lay, ch in ((pcbnew.F_Cu, "F"), (pcbnew.B_Cu, "B")):
        p = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
        s += ch if zs[lay].HitTestFilledArea(lay, p) else "."
    return s

print("    " + "".join(str(int(x) % 10) for x in range(0, 100, 2)))
for y in range(0, 64, 2):
    print(f"{y:3d} " + "".join(mark(x + 1.0, y + 1.0) for x in range(0, 100, 2)))
