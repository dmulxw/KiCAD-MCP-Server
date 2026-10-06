"""Topology of the thirty-one strip nets: where does each one actually run?

Each net is a set of track segments plus pads.  The interesting parts are the
two ends of the net: the end at J1, where the signals currently enter the board,
and the end out in the key matrix.  Print both, plus the bounding box, so the
placement can be reasoned about instead of guessed.

  python _tp_topo.py [NET ...]
"""
import re
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

WANT = re.compile(r"^(ROW\d+|CSEL\d+)$")
SEL = [a for a in sys.argv[1:] if not a.startswith("-")]

b = pcbnew.LoadBoard(PCB)

segs = {}
pads = {}
for t in b.GetTracks():
    nm = t.GetNetname().lstrip("/")
    if not WANT.match(nm):
        continue
    s, e = t.GetStart(), t.GetEnd()
    if isinstance(t, pcbnew.PCB_VIA):
        continue                      # vias carry no direction; skip the fanout
    segs.setdefault(nm, []).append(
        (b.GetLayerName(t.GetLayer()),
         pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
         pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
         pcbnew.ToMM(t.GetWidth())))
for fp in b.GetFootprints():
    for p in fp.Pads():
        nm = p.GetNetname().lstrip("/")
        if WANT.match(nm):
            q = p.GetPosition()
            pads.setdefault(nm, []).append(
                (fp.GetReference(), p.GetNumber(),
                 pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)))

# J1's pad row, where the signals enter today
J1X0, J1X1, J1Y = 125.75, 145.25, 243.15

print("net      segs  len(mm)   bbox x0..x1  y0..y1      J1-side end"
      "        matrix-side end")
def sortkey(n):
    return (n[:3], int(n[3:]) if n.startswith("ROW") else int(n[4:]))


for nm in sorted(segs, key=sortkey):
    if SEL and nm not in SEL:
        continue
    ss = segs[nm]
    ln = sum(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
             for _, x0, y0, x1, y1, _ in ss)
    xs = [v for _, x0, y0, x1, y1, _ in ss for v in (x0, x1)]
    ys = [v for _, x0, y0, x1, y1, _ in ss for v in (y0, y1)]
    for _, _, x, y in pads.get(nm, []):
        xs.append(x)
        ys.append(y)
    near = []
    far = []
    for _, x0, y0, x1, y1, _ in ss:
        for x, y in ((x0, y0), (x1, y1)):
            d = ((x - (J1X0 + J1X1) / 2) ** 2 + (y - J1Y) ** 2) ** 0.5
            near.append((d, x, y))
            far.append((-d, x, y))
    near.sort()
    far.sort()
    print("%-7s %5d  %7.1f   %6.1f..%6.1f %6.1f..%6.1f   "
          "(%6.1f,%6.1f) d=%5.1f   (%6.1f,%6.1f) d=%5.1f"
          % (nm, len(ss), ln, min(xs), max(xs), min(ys), max(ys),
             near[0][1], near[0][2], near[0][0],
             far[0][1], far[0][2], -far[0][0]))

print("\n=== pads per net (reference.pad) nearest the matrix, sample")
for nm in sorted(pads, key=sortkey):
    if SEL and nm not in SEL:
        continue
    pl = pads[nm]
    print("   %-7s %3d pad(s)   e.g. %s"
          % (nm, len(pl),
             "  ".join("%s.%s" % (r, p) for r, p, _, _ in pl[:6])))
