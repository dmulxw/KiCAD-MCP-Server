"""What footprint contains (54.75, 20.075) and (60.0, 20.825)?

VIA_BAN is (43,11)-(74,32) -- a 31x21 mm box that swallows R6..R9 whole and
forbids every via around them.  If that box is the ESP32 module, then R6-R9
are sitting under it, and the "cannot reach pad" is a placement error, not a
routing one.

  python _probe_owner.py
"""
import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
board = pcbnew.LoadBoard(HERE + r"\YD-ESP32-S3-Carrier.kicad_pcb")

pts = [(54.75, 20.075), (60.0, 20.825), (48.0, 20.825), (65.6, 20.825)]

for f in board.GetFootprints():
    bb = f.GetBoundingBox()
    x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
    hits = [p for p in pts if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
    if not hits:
        continue
    pos = f.GetPosition()
    print("%-8s %-34s at (%7.2f,%7.2f) rot=%-5.1f bbox x[%7.2f..%7.2f] y[%7.2f..%7.2f]"
          % (f.GetReference(), f.GetFPID().GetLibItemName(),
             pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), f.GetOrientationDegrees(),
             x0, x1, y0, y1))
    print("         contains: %s" % ", ".join("(%.2f,%.2f)" % p for p in hits))

print("\n-- VIA_BAN box (43,11)-(74,32): footprints overlapping it --")
for f in board.GetFootprints():
    bb = f.GetBoundingBox()
    x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
    if x1 < 43 or x0 > 74 or y1 < 11 or y0 > 32:
        continue
    pos = f.GetPosition()
    print("   %-8s %-34s at (%7.2f,%7.2f)  bbox x[%7.2f..%7.2f] y[%7.2f..%7.2f]"
          % (f.GetReference(), f.GetFPID().GetLibItemName(),
             pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), x0, x1, y0, y1))
