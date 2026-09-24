import math, pcbnew
BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
b = pcbnew.LoadBoard(BOARD)
CX, CY = 44.00, 42.50
R = 6.0
print(f"--- everything within {R} mm of C1 pad2 ({CX},{CY}) ---")
for fp in b.GetFootprints():
    for p in fp.Pads():
        x, y = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        d = math.hypot(x - CX, y - CY)
        if d < R:
            print(f"  pad  {fp.GetReference()}.{p.GetNumber():<3} {p.GetNetname():<10} "
                  f"({x:7.3f},{y:7.3f}) d={d:5.2f} size=({pcbnew.ToMM(p.GetSize().x):.2f}x"
                  f"{pcbnew.ToMM(p.GetSize().y):.2f})")
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        x, y = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)
        d = math.hypot(x - CX, y - CY)
        if d < R:
            print(f"  via  {t.GetNetname():<10} ({x:7.3f},{y:7.3f}) d={d:5.2f}")
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = (pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), pcbnew.ToMM(e.x), pcbnew.ToMM(e.y))
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    u = 0.0 if l2 == 0 else max(0.0, min(1.0, ((CX - x1) * dx + (CY - y1) * dy) / l2))
    d = math.hypot(CX - (x1 + u * dx), CY - (y1 + u * dy))
    if d < R:
        print(f"  trk  {t.GetNetname():<10} ({x1:7.3f},{y1:7.3f})-({x2:7.3f},{y2:7.3f}) "
              f"w={pcbnew.ToMM(t.GetWidth()):.2f} d={d:5.2f} layer={t.GetLayer()}")
