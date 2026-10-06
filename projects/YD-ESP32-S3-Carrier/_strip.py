"""The strip's actual geometry: who is where, and which pin wants which pin.

Every routing decision on the 74HC595 strip depends on two facts this prints:
where the four connectors' pad rows actually sit, and -- for each strip net --
the straight-line distance from the shift register's output to the header pin
it has to reach.  A net far longer than that distance needs a detour, and a
cluster of them all wanting to cross the same gap is the congestion to plan
around, not to discover one failure at a time.

  python _strip.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
S = 1e6
b = pcbnew.LoadBoard(BOARD)

STRIP = ["J8", "J10", "U3", "U4", "U5", "U6"]


def rows(ref):
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        return None
    pads = []
    for p in fp.Pads():
        c = p.GetPosition()
        bb = p.GetBoundingBox()
        pads.append((str(p.GetNumber()), c.x / S, c.y / S,
                     bb.GetLeft() / S, bb.GetTop() / S,
                     bb.GetRight() / S, bb.GetBottom() / S,
                     p.GetNetname(), p.GetAttribute()))
    return fp, pads


print("=== pad rows ===")
for ref in STRIP:
    got = rows(ref)
    if got is None:
        print("%-5s  MISSING" % ref)
        continue
    fp, pads = got
    xs = [p[1] for p in pads]
    ys = [p[2] for p in pads]
    c = fp.GetPosition()
    print("%-5s  n=%-3d centre(%.2f,%.2f)  x %.2f..%.2f  y %.2f..%.2f"
          % (ref, len(pads), c.x / S, c.y / S, min(xs), max(xs), min(ys), max(ys)))
    # distinct rows (y values) tell you whether it is one row or two
    yset = sorted({round(p[2], 2) for p in pads})
    if len(yset) > 1:
        print("        rows at y = %s" % ", ".join("%.2f" % v for v in yset))
    if pads:
        px = sorted(p[1] for p in pads)
        d = [round(px[i + 1] - px[i], 3) for i in range(len(px) - 1)]
        d = sorted(set(d))
        print("        pitch(es) x = %s" % ", ".join("%.3f" % v for v in d[:4]))
        w = max(p[5] - p[3] for p in pads)
        h = max(p[6] - p[4] for p in pads)
        print("        pad bbox max  %.3f x %.3f" % (w, h))

print("\n=== strip nets: output pad -> header pad ===")
seen = {}
for fp in b.GetFootprints():
    for p in fp.Pads():
        nm = p.GetNetname()
        if not nm or not (nm.startswith("ROW") or nm.startswith("CSEL")):
            continue
        c = p.GetPosition()
        seen.setdefault(nm, []).append(
            ("%s.%s" % (fp.GetReference(), p.GetNumber()), c.x / S, c.y / S))

tot = 0.0
for nm in sorted(seen, key=lambda s: (s[:3], int(s[3:])) if s[3:].isdigit() else (s, 0)):
    ends = seen[nm]
    line = "%-7s" % nm
    pts = []
    for lbl, x, y in ends:
        line += "  %-7s (%6.2f,%6.2f)" % (lbl, x, y)
        pts.append((x, y))
    if len(pts) == 2:
        d = ((pts[0][0] - pts[1][0]) ** 2 + (pts[0][1] - pts[1][1]) ** 2) ** 0.5
        tot += d
        line += "   straight %.1f" % d
    print(line)
print("\n%d strip net(s), %.0f mm of straight-line distance in total"
      % (len(seen), tot))
