"""Why are 23 GND stitching vias reported dangling and unconnected?"""
import pcbnew, collections

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
board = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM

zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
print("zones:", [(z.GetNetname(), z.GetLayerSet().FmtHex()) for z in zones])

polys = {}   # layer -> list of SHAPE_POLY_SET outlines
for z in zones:
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        if not z.GetLayerSet().Contains(layer):
            continue
        ps = z.GetFilledPolysList(layer)
        if ps.OutlineCount() == 0:
            continue
        polys.setdefault(layer, []).append((ps, z.GetNetname()))

def inside(layer, x, y):
    p = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
    for ps, net in polys.get(layer, []):
        if ps.Contains(p):
            return net
    return None

bad = []
for t in board.GetTracks():
    if t.GetClass() != "PCB_VIA" or t.GetNetname() != "GND":
        continue
    x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
    f, b = inside(pcbnew.F_Cu, x, y), inside(pcbnew.B_Cu, x, y)
    if f is None or b is None:
        bad.append((x, y, f, b))

print(f"\nGND vias with no fill under them on at least one layer: {len(bad)}")
for x, y, f, b in sorted(bad):
    print(f"  ({x:6.2f},{y:6.2f})  F.Cu={f}  B.Cu={b}")

# take one of them and look at what is around
if bad:
    x, y = bad[0][0], bad[0][1]
    print(f"\n--- around ({x},{y}) ---")
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        s, e = t.GetStart(), t.GetEnd()
        d = min(abs(mm(s.x)-x)+abs(mm(s.y)-y), abs(mm(e.x)-x)+abs(mm(e.y)-y))
        if d < 4:
            print(f"  {t.GetNetname():<12} {t.GetLayerName():<6} "
                  f"({mm(s.x):.2f},{mm(s.y):.2f})-({mm(e.x):.2f},{mm(e.y):.2f}) w={mm(t.GetWidth()):.2f}")
