"""J1/J2 pad geometry and what sits below the ESP32-S3."""
import sys
import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
TO = pcbnew.ToMM
b = pcbnew.LoadBoard(BOARD)

for ref in ("J1", "J2", "J8", "J10", "J3", "J5", "J9"):
    f = b.FindFootprintByReference(ref)
    if not f:
        print("%s not found" % ref)
        continue
    p = f.GetPosition()
    ps = sorted(f.Pads(), key=lambda q: (TO(q.GetPosition().y), TO(q.GetPosition().x)))
    ys = [TO(q.GetPosition().y) for q in ps]
    xs = [TO(q.GetPosition().x) for q in ps]
    print("%-4s %-34s origin (%8.3f,%8.3f) rot %6.1f  %2d pads" %
          (ref, str(f.GetValue())[:34], TO(p.x), TO(p.y), f.GetOrientationDegrees(), len(ps)))
    print("     pad1 (%8.3f,%8.3f)   x %8.3f..%8.3f  y %8.3f..%8.3f  span %.2f mm"
          % (TO(ps[0].GetPosition().x), TO(ps[0].GetPosition().y),
             min(xs), max(xs), min(ys), max(ys), max(ys) - min(ys)))
