"""Put U1-U4 and C1-C4 onto the touch panel, with their nets.

The schematic already has them (U1 drives ROW0-7, U2 ROW8-15, U3 ROW16-20 then
CSEL0-2, U4 CSEL3-9, cascaded U1->U2->U3->U4).  The board has never been
synced, so the parts do not exist here and J1 still carries the old row and
column nets.

They go in the left corridor (x 90.70..99.70, y 165.95..249.45), stacked at
20 mm pitch, which is the only sizeable clear area on the board.

  python _tp_add.py [--rot 180] [--dry]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
FPDIR = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"

argv = sys.argv[1:]
ROT = float(argv[argv.index("--rot") + 1]) if "--rot" in argv else 180.0
DRY = "--dry" in argv

CX = 95.20
NOUT = "Package_SO"
NCAP = "Capacitor_SMD"
SOIC = "SOIC-16_3.9x9.9mm_P1.27mm"
CAP = "C_0402_1005Metric"

# pin -> net, per chip
CHIPS = [
    ("U1", 173.00, {15: "ROW0", 1: "ROW1", 2: "ROW2", 3: "ROW3", 4: "ROW4",
                    5: "ROW5", 6: "ROW6", 7: "ROW7",
                    8: "GND", 16: "+3V3", 10: "+3V3",
                    11: "IO10", 12: "IO11", 13: "IO12", 14: "IO9",
                    9: "DRV_CASC1"}),
    ("U2", 193.00, {15: "ROW8", 1: "ROW9", 2: "ROW10", 3: "ROW11",
                    4: "ROW12", 5: "ROW13", 6: "ROW14", 7: "ROW15",
                    8: "GND", 16: "+3V3", 10: "+3V3",
                    11: "IO10", 12: "IO11", 13: "IO12", 14: "DRV_CASC1",
                    9: "DRV_CASC2"}),
    ("U3", 213.00, {15: "ROW16", 1: "ROW17", 2: "ROW18", 3: "ROW19",
                    4: "ROW20", 5: "CSEL0", 6: "CSEL1", 7: "CSEL2",
                    8: "GND", 16: "+3V3", 10: "+3V3",
                    11: "IO10", 12: "IO11", 13: "IO12", 14: "DRV_CASC2",
                    9: "DRV_CASC3"}),
    ("U4", 233.00, {15: "CSEL3", 1: "CSEL4", 2: "CSEL5", 3: "CSEL6",
                    4: "CSEL7", 5: "CSEL8", 6: "CSEL9",
                    8: "GND", 16: "+3V3", 10: "+3V3",
                    11: "IO10", 12: "IO11", 13: "IO12", 14: "DRV_CASC3"}),
]
CAPS = [("C1", 180.50), ("C2", 200.50), ("C3", 220.50), ("C4", 240.50)]

b = pcbnew.LoadBoard(PCB)

have = set()
for code, ni in b.GetNetInfo().NetsByNetcode().items():
    have.add(ni.GetNetname().lstrip("/"))


def net(name):
    ni = b.FindNet(name)
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(b, name)
        b.Add(ni)
        print("   + new net %s" % name)
    return ni


def place(ref, value, lib, name, x, y, rot):
    fp = pcbnew.FootprintLoad("%s\\%s.pretty" % (FPDIR, lib), name)
    if fp is None:
        raise SystemExit("cannot load %s from %s" % (name, lib))
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    fp.SetOrientationDegrees(rot)
    b.Add(fp)
    return fp


print("placing (rot %.0f)" % ROT)
made = []
for ref, y, pins in CHIPS:
    fp = place(ref, "74HC595", NOUT, SOIC, CX, y, ROT)
    made.append(fp)
    for p in fp.Pads():
        n = pins.get(int(p.GetNumber()))
        if n:
            p.SetNet(net(n))
for ref, y in CAPS:
    fp = place(ref, "100nF", NCAP, CAP, 92.00, y, ROT)
    made.append(fp)
    for p in fp.Pads():
        p.SetNet(net("+3V3" if p.GetNumber() == "1" else "GND"))

print("\nplaced pads (x, y, side of body centre, net)")
for fp in made:
    c = fp.GetPosition()
    cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
    r = fp.GetBoundingBox()
    print("\n%-4s at (%.2f, %.2f) rot %.0f   bbox %.2f x %.2f"
          % (fp.GetReference(), cx, cy, fp.GetOrientationDegrees(),
             pcbnew.ToMM(r.GetWidth()), pcbnew.ToMM(r.GetHeight())))
    rows = []
    for p in fp.Pads():
        q = p.GetPosition()
        px, py = pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
        rows.append((py, p.GetNumber(), px, py, p.GetNetname().lstrip("/")))
    for py, num, px, _py, nm in sorted(rows):
        side = "E" if px > cx + 0.1 else ("W" if px < cx - 0.1 else "-")
        print("     pin %-3s %s  (%6.2f, %6.2f)  %s" % (num, side, px, py, nm))

if DRY:
    print("\n--dry: not saved")
else:
    b.Save(PCB)
    print("\nsaved %s" % PCB)
