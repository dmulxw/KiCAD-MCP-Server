"""Where the 595s sit relative to the header and to what they have to drive.

The 13 nets that will not route all end in the bottom band y 242.5..246.85,
x 112..158 -- the CSEL resistor row -- while the 595s sit in a column at x 95.20.
If that is the wrong side of the board for 7 of the 10 CSEL outputs, no amount of
router tuning fixes it and the answer is placement, not routing.  Prints the
connectors and the 595s, then each blocked net's pads and the span it implies.
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)

print("=== connectors and larger parts ===")
rows = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    pads = list(fp.Pads())
    if len(pads) >= 8 or ref[0] in "JU":
        bb = fp.GetBoundingBox()
        pos = fp.GetPosition()
        rows.append((ref, len(pads), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                     pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()),
                     fp.GetFPID().GetLibItemName()))
for r in sorted(rows, key=lambda t: (t[2], t[3])):
    print("  %-5s %2d pad  at (%7.3f,%7.3f)  %.1f x %.1f  %s"
          % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))

print("\n=== where each blocked net's pads actually are ===")
want = ["CSEL2", "CSEL3", "CSEL5", "CSEL6", "CSEL7", "CSEL8", "CSEL9",
        "IO9", "IO10", "IO11", "IO12", "+3V3", "ROW8"]
pads = {}
for fp in board.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if n in want:
            pos = p.GetPosition()
            pads.setdefault(n, []).append(
                (fp.GetReference(), p.GetNumber(),
                 pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)))
for n in want:
    pts = pads.get(n, [])
    if not pts:
        print("  %-7s (no pads)" % n)
        continue
    xs = [p[2] for p in pts]
    ys = [p[3] for p in pts]
    span = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
    print("  %-7s %d pad(s)  x %7.2f..%7.2f  y %7.2f..%7.2f  span %5.1f mm"
          % (n, len(pts), min(xs), max(xs), min(ys), max(ys), span))
    for (ref, num, x, y) in sorted(pts, key=lambda t: t[3]):
        print("             %-5s.%-3s (%7.3f,%7.3f)" % (ref, num, x, y))
