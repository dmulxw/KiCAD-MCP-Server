"""Move the panel interface from "J1 drives the matrix" to "J1 is just a bus".

J1's footprint stays; only its pad nets change.  Pads 1-4 become IO9..IO12 and
5-31 join 32-36 on GND, matching the schematic and the carrier's J8/J10.

That is not enough on its own.  Every ROW*/CSEL* net still has copper running
back to its old J1 pad, and once those pads are GND that copper is a row shorted
to ground.  The feeder is woven through the matrix rather than gathered in a
band, so it is cut geometrically: any row/column track whose segment enters a
box around the connector is removed.  The matrix away from J1 is untouched, and
what is left behind is a dead-end stub on a net that is still driven -- legal,
just untidy.

GND then needs one more thing the router will not supply: route.py skips GND
outright, so a single bus along the pad row ties 5-31 to the already-connected
32-36.

Every pad coordinate is read into plain Python before anything is removed.  SWIG
invalidates the proxies of live objects when siblings are deleted, so touching
j1.Pads() after a Remove() hands back raw SwigPyObjects.

  python _tp_j1fix.py [--padbox 1.0] [--dry]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

argv = sys.argv[1:]
PADBOX = float(argv[argv.index("--padbox") + 1]) if "--padbox" in argv else 1.0
DRY = "--dry" in argv

NEW = {}
for i in range(1, 5):
    NEW[str(i)] = ["IO9", "IO10", "IO11", "IO12"][i - 1]
for i in range(5, 37):
    NEW[str(i)] = "GND"
for i in range(37, 41):
    NEW[str(i)] = "+3V3"

# Removed proxies must outlive the board's own bookkeeping; see clear_routing()
# in the carrier's route.py.  Dropping them corrupts SWIG's object table.
KEEP = []

b = pcbnew.LoadBoard(PCB)
j1 = b.FindFootprintByReference("J1")
if j1 is None:
    raise SystemExit("no J1")


def net(name):
    ni = b.FindNet(name)
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(b, name)
        b.Add(ni)
        print("   + new net %s" % name)
    return ni


# -- read every pad into plain data first ------------------------------------
pads = []          # (number, x, y, netname, bb_left, bb_top, bb_right, bb_bottom)
for p in j1.Pads():
    pos = p.GetPosition()
    bb = p.GetBoundingBox()
    pads.append((p.GetNumber(), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                 p.GetNetname().lstrip("/"),
                 pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                 pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
print("J1 has %d pad(s)" % len(pads))

# -- reassign ----------------------------------------------------------------
changed = 0
for p in j1.Pads():
    want = NEW.get(p.GetNumber())
    if want and p.GetNetname().lstrip("/") != want:
        p.SetNet(net(want))
        changed += 1
print("reassigned %d pad(s) on J1" % changed)

# -- cut box -----------------------------------------------------------------
bx0 = min(t[4] for t in pads) - PADBOX
by0 = min(t[5] for t in pads) - PADBOX
bx1 = max(t[6] for t in pads) + PADBOX
by1 = max(t[7] for t in pads) + PADBOX
print("cut box x %.2f..%.2f  y %.2f..%.2f" % (bx0, bx1, by0, by1))


def seg_hits_box(x1, y1, x2, y2, x0, y0, x1b, y1b):
    """Liang-Barsky clip of a segment against an axis-aligned box."""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x1 - x0), (dx, x1b - x1), (-dy, y1 - y0), (dy, y1b - y1)):
        if abs(pp) < 1e-12:
            if qq < 0:
                return False
            continue
        r = qq / pp
        if pp < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


cut = 0
for t in list(b.GetTracks()):
    par = t.GetParent()
    if par is not None and par.GetClass() == "FOOTPRINT":
        continue
    nm = t.GetNetname().lstrip("/")
    if not (nm.startswith("ROW") or nm.startswith("CSEL")):
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        pos = t.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        hit = bx0 <= x <= bx1 and by0 <= y <= by1
    else:
        s, e = t.GetStart(), t.GetEnd()
        hit = seg_hits_box(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
                           pcbnew.ToMM(e.x), pcbnew.ToMM(e.y), bx0, by0, bx1, by1)
    if hit:
        b.Remove(t)
        KEEP.append(t)
        cut += 1
print("row/column tracks cut: %d" % cut)

# -- gnd bus -----------------------------------------------------------------
gp = sorted((int(t[0]), t[1], t[2]) for t in pads if NEW.get(t[0]) == "GND")
low = [g for g in gp if g[0] <= 31]
high = [g for g in gp if g[0] >= 32]
print("gnd pads on J1: %d   new(5-31)=%d  already(32-36)=%d"
      % (len(gp), len(low), len(high)))
if low and high:
    y = low[0][2]
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(low[0][1]), pcbnew.FromMM(y)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(high[-1][1]), pcbnew.FromMM(y)))
    t.SetWidth(pcbnew.FromMM(0.25))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNetCode(net("GND").GetNetCode())
    b.Add(t)
    KEEP.append(t)
    print("  gnd bus F.Cu y=%.2f  x %.2f -> %.2f" % (y, low[0][1], high[-1][1]))

if DRY:
    print("\n--dry: not saved")
else:
    b.Save(PCB)
    print("\nsaved")
