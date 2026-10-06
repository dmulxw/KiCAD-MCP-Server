"""How much copper actually has to change?

The row and column nets keep their names after the migration -- only their
driver moves from J1 to the 595s.  What matters is whether the old feeder
copper from J1 can be dropped without dragging the whole matrix along, so
count the tracks and length on those nets versus everything else, and check
that the footprints we intend to add can actually be loaded.

  python _tp_scope.py
"""
import os
import re

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
FPDIR = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"

MOVE = re.compile(r"^(ROW\d+|CSEL\d+)$")

b = pcbnew.LoadBoard(PCB)

tot = mov = 0
movlen = totlen = 0
byname = {}
for t in b.GetTracks():
    nm = t.GetNetname().lstrip("/")
    ln = pcbnew.ToMM(t.GetLength())
    tot += 1
    totlen += ln
    if MOVE.match(nm):
        mov += 1
        movlen += ln
        byname[nm] = byname.get(nm, 0) + 1

print("tracks total          %5d   %9.1f mm" % (tot, totlen))
print("on ROW*/CSEL*         %5d   %9.1f mm  (%.0f%% of length)"
      % (mov, movlen, 100.0 * movlen / totlen))
print("everything else       %5d   %9.1f mm" % (tot - mov, totlen - movlen))
print("\nper net:")
for nm in sorted(byname, key=lambda n: (0, int(n[3:])) if n.startswith("ROW")
                 else (1, int(n[4:]))):
    print("   %-8s %4d" % (nm, byname[nm]))

print("\n=== nets present on the board that matter for the swap")
for want in ("IO9", "IO10", "IO11", "IO12",
             "DRV_CASC1", "DRV_CASC2", "DRV_CASC3", "+3V3", "GND"):
    ni = b.FindNet(want)
    print("   %-10s %s" % (want, "exists" if ni else "-- must be added --"))

print("\n=== footprint library availability")
for lib, name in (
        ("Package_SO", "SOIC-16_3.9x9.9mm_P1.27mm"),
        ("Capacitor_SMD", "C_0402_1005Metric"),
        ("Resistor_SMD", "R_0402_1005Metric")):
    path = os.path.join(FPDIR, lib + ".pretty")
    ok = os.path.isdir(path)
    fp = pcbnew.FootprintLoad(path, name) if ok else None
    if fp:
        r = fp.GetBoundingBox()
        print("   %-14s %-32s OK  bbox %.2f x %.2f mm"
              % (lib, name, pcbnew.ToMM(r.GetWidth()),
                 pcbnew.ToMM(r.GetHeight())))
    else:
        print("   %-14s %-32s MISSING (%s)" % (lib, name, path))
