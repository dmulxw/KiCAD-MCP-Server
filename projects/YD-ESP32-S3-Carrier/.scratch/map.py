"""Text map of what the filler actually poured between J1 and J2, so the shape
of the empty bay is visible rather than inferred from vertex tallies."""
import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM
zones = {zz.GetLayer(): zz for zz in b.Zones() if not zz.GetIsRuleArea()}

def mark(x, y):
    s = ""
    for lay, ch in ((pcbnew.F_Cu, "F"), (pcbnew.B_Cu, "B")):
        p = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
        s += ch if zones[lay].HitTestFilledArea(lay, p) else "."
    return s

xs = [9 + i for i in range(32)]          # x 9 .. 40
ys = [y * 1.0 for y in range(6, 65)]     # y 6 .. 64
print("     " + "".join(str(int(x) % 10) for x in xs))
for y in ys:
    row = "".join(mark(x + 0.5, y + 0.5) for x in xs)
    print(f"{int(y):4d} {row}")
