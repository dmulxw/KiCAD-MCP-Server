"""What holds the last two GND islands up?

_fix_islands.py says neither has a legal via spot: every cell's opposite-layer
neighbour is either part of the same island or bare board.  An island with no
neighbour to reach and no pad to anchor on is exactly what "remove islands" is
supposed to delete, so either the anchor is there and the scan is not seeing it,
or the setting is not doing what its name suggests.  Print the pads.

  python _probe_two.py [board.kicad_pcb]
"""
import sys

import pcbnew

BOARD = sys.argv[1] if len(sys.argv) > 1 else (
    r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
    r"\_v90.kicad_pcb")

RECTS = {"16.6 mm2": (79.20, 43.60, 83.60, 47.40),
         "1.0 mm2": (49.40, 59.20, 50.80, 60.00)}

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)
TO = pcbnew.ToMM

for name, (x0, y0, x1, y1) in RECTS.items():
    print("=== %s  x %.2f..%.2f  y %.2f..%.2f ===" % (name, x0, y0, x1, y1))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            px, py = TO(pos.x), TO(pos.y)
            if not (x0 - 1.5 <= px <= x1 + 1.5 and y0 - 1.5 <= py <= y1 + 1.5):
                continue
            lays = ",".join(board.GetLayerName(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)
                            if p.IsOnLayer(l))
            print("  pad %-6s (%7.3f,%7.3f)  net %-6s  %.2fx%.2f  %s  drill %.2f"
                  % (str(fp.GetReference()) + "." + str(p.GetNumber()), px, py,
                     str(p.GetNetname()),
                     TO(p.GetSize().x), TO(p.GetSize().y), lays,
                     TO(p.GetDrillSize().x)))
    n = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND":
            pos = t.GetPosition()
            px, py = TO(pos.x), TO(pos.y)
            if x0 - 1.5 <= px <= x1 + 1.5 and y0 - 1.5 <= py <= y1 + 1.5:
                print("  GND via at (%7.3f,%7.3f)" % (px, py))
                n += 1
    print("  (%d GND via(s) in the neighbourhood)" % n)

print("\n=== GND zones on this board ===")
for z in board.Zones():
    if str(z.GetNetname()) != "GND":
        continue
    print("  %-5s  rule_area=%s  pad_conn=%d  min_thick=%.3f  "
          "island_mode=%s  island_area_min=%.2f  clearance=%.3f"
          % (board.GetLayerName(z.GetLayer()) if not z.IsOnLayer(pcbnew.F_Cu)
             else "F.Cu",
             z.GetIsRuleArea(), z.GetPadConnection(),
             TO(z.GetMinThickness()),
             getattr(z, "GetIslandRemovalMode", lambda: "n/a")(),
             TO(getattr(z, "GetMinIslandArea", lambda: 0)()),
             TO(z.GetLocalClearance())))
    print("        filled polys %d outline(s) on F.Cu, %d on B.Cu"
          % (z.GetFilledPolysList(pcbnew.F_Cu).OutlineCount(),
             z.GetFilledPolysList(pcbnew.B_Cu).OutlineCount()))
