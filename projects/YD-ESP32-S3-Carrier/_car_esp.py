"""Where are the ESP32-S3 socket rows, and what is around them?"""
import sys
import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
TO = pcbnew.ToMM
b = pcbnew.LoadBoard(BOARD)
if b is None:
    sys.exit("LoadBoard returned None")

bb = b.GetBoardEdgesBoundingBox()
print("board edges: x %.2f..%.2f  y %.2f..%.2f  (%.2f x %.2f mm)"
      % (TO(bb.GetLeft()), TO(bb.GetRight()), TO(bb.GetTop()), TO(bb.GetBottom()),
         TO(bb.GetWidth()), TO(bb.GetHeight())))

print("\n=== footprints, sorted by y ===")
rows = []
for f in b.GetFootprints():
    p = f.GetPosition()
    pb = f.GetBoundingBox()
    rows.append((TO(p.y), TO(p.x), f.GetReference(), str(f.GetValue()),
                 str(f.GetFPID().GetLibItemName()),
                 TO(pb.GetWidth()), TO(pb.GetHeight()),
                 TO(pb.GetLeft()), TO(pb.GetTop()), TO(pb.GetRight()), TO(pb.GetBottom()),
                 int(f.GetPadCount())))
for (y, x, ref, val, fpid, w, h, l, t, r, bt, npad) in sorted(rows):
    print("  %-6s (%8.3f,%8.3f) %-28s %-40s %2d pads  bbox x %7.2f..%7.2f y %7.2f..%7.2f"
          % (ref, x, y, val[:28], fpid[:40], npad, l, r, t, bt))
