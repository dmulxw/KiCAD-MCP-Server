"""What nets the carrier PCB currently has on J8/J10, pad by pad.

The schematic has no labels on either connector, so the pad nets on the board
are the only record of the old 40-pin interface -- and the thing that has to be
replaced.  Read them off the board rather than trusting a transcript.
"""
import pcbnew

PCB = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
       r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(PCB)
print("board %s" % PCB)
print("footprints %d, tracks %d" % (len(b.GetFootprints()), len(b.GetTracks())))

for ref in ("J8", "J10"):
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        print("%s: not found" % ref)
        continue
    pos = fp.GetPosition()
    print("\n=== %-4s %-46s at (%.2f, %.2f) rot %.0f layer %s  %d pad(s)"
          % (ref, str(fp.GetFPID()), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
             fp.GetOrientationDegrees(), fp.GetLayerName(),
             len(fp.Pads())))
    pads = []
    for p in fp.Pads():
        pp = p.GetPosition()
        pads.append((p.GetNumber(), pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y),
                     p.GetNetname()))
    for num, x, y, net in sorted(pads, key=lambda t: int(t[0])):
        print("   pad %-3s (%7.2f,%7.2f)  %s"
              % (num, x, y, net if net else "-- unassigned --"))
