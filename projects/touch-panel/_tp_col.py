"""What is sitting in the x = 101.6 column?

Every strip net turns up with a pad near x 101.6, 2.2 mm above its row line.
Find the footprint that owns those pads -- if it is a header tapping all the
rows, it is where new drivers should land.

  python _tp_col.py [--x 101.6] [--tol 1.5]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

argv = sys.argv[1:]
X = float(argv[argv.index("--x") + 1]) if "--x" in argv else 101.6
TOL = float(argv[argv.index("--tol") + 1]) if "--tol" in argv else 1.5

b = pcbnew.LoadBoard(PCB)

byref = {}
for fp in b.GetFootprints():
    for p in fp.Pads():
        q = p.GetPosition()
        x, y = pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
        if abs(x - X) <= TOL:
            byref.setdefault(fp.GetReference(), []).append(
                (fp, p.GetNumber(), x, y, p.GetNetname().lstrip("/")))

print("footprints with a pad within %.1f mm of x = %.1f" % (TOL, X))
for ref in sorted(byref, key=lambda r: (len(r), r)):
    fps = {id(f): f for f, _, _, _, _ in byref[ref]}
    fp = list(fps.values())[0]
    pads = sorted(byref[ref], key=lambda t: t[3])
    print("\n%-6s %-40s at (%.2f, %.2f) rot %.0f  layer %s  %d pad(s) in band"
          % (ref, fp.GetFPID().GetLibItemName() or "<empty fpid>",
             pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y),
             fp.GetOrientationDegrees(),
             b.GetLayerName(fp.GetLayer()), len(pads)))
    print("       pads total %d" % len(list(fp.Pads())))
    for _, num, x, y, net in pads[:24]:
        print("         pad %-4s (%.2f, %.2f)  %s" % (num, x, y, net))

print("\n=== footprints with an empty library id")
for fp in b.GetFootprints():
    if not fp.GetFPID().GetLibItemName():
        q = fp.GetPosition()
        print("   %-6s at (%.2f, %.2f) rot %.0f  %d pad(s)  nets %s"
              % (fp.GetReference(), pcbnew.ToMM(q.x), pcbnew.ToMM(q.y),
                 fp.GetOrientationDegrees(), len(list(fp.Pads())),
                 sorted({p.GetNetname().lstrip("/") for p in fp.Pads()})[:6]))
