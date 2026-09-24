import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM
PROBES = [(20, 20), (20, 26), (28, 28), (50, 20), (90, 50)]
for n, z in enumerate(b.Zones()):
    if z.GetIsRuleArea():
        continue
    layer = "F.Cu" if z.GetLayer() == pcbnew.F_Cu else "B.Cu"
    poly = z.GetFilledPolysList(z.GetLayer())
    print(f"--- zone {n} {layer}  outlines={poly.OutlineCount()} area={poly.Area()/1e12:.1f} mm2",
          flush=True)
    for i in range(poly.OutlineCount()):
        ol = poly.Outline(i)
        bb = ol.BBox()
        cnt = [p for p in PROBES if poly.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])), i)]
        print(f"   outline {i}: x {mm(bb.GetLeft()):6.2f}..{mm(bb.GetRight()):<6.2f}"
              f" y {mm(bb.GetTop()):6.2f}..{mm(bb.GetBottom()):<6.2f}"
              f" pts {ol.PointCount():5d} hole {poly.HoleCount(i)}"
              f" contains {cnt}", flush=True)
