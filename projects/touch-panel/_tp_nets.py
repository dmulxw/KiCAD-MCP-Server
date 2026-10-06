"""Where the strip lines physically run on the touch panel.

The shift registers are about to be placed on this board, and their outputs have
to reach all thirty-one ROW/CSEL nets.  That is only a routing problem if the
nets are somewhere sensible, so first find out what each one touches and how far
it spreads -- and in particular whether the connector pads that used to bring
these signals in are still the natural gathering point.

  python _tp_nets.py [--sch PATH] [--all]
"""
import re
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCAD-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
WANT = re.compile(r"^(ROW\d+|CSEL\d+)$")
SHOW_ALL = "--all" in sys.argv

b = pcbnew.LoadBoard(PCB)

want = {}
for code, net in b.GetNetInfo().NetsByNetcode().items():
    nm = net.GetNetname().lstrip("/")
    if WANT.match(nm) or SHOW_ALL:
        want[nm] = code

print("%d net(s) of interest\n" % len(want))


def num(nm):
    m = re.match(r"([A-Z]+)(\d+)", nm)
    return (m.group(1), int(m.group(2)))


for nm in sorted(want, key=num):
    code = want[nm]
    pads = []
    xs, ys = [], []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == code:
                pp = p.GetPosition()
                px, py = pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)
                pads.append((fp.GetReference(), p.GetNumber()))
                xs.append(px)
                ys.append(py)
    segs = 0
    for t in b.GetTracks():
        if t.GetNetCode() == code:
            segs += 1
            bb = t.GetBoundingBox()
            xs.append(pcbnew.ToMM(bb.GetX()))
            xs.append(pcbnew.ToMM(bb.GetX() + bb.GetWidth()))
            ys.append(pcbnew.ToMM(bb.GetY()))
            ys.append(pcbnew.ToMM(bb.GetY() + bb.GetHeight()))
    conn = sorted({r for r, _p in pads if r in ("J1", "J1A", "J1B")})
    print("%-7s %3d pad(s) %4d seg(s)  x %6.2f..%6.2f  y %6.2f..%6.2f  %s"
          % (nm, len(pads), segs, min(xs) if xs else 0, max(xs) if xs else 0,
             min(ys) if ys else 0, max(ys) if ys else 0,
             ("connector pads: " + ",".join(conn)) if conn else ""))

print("\n--- pad detail")
for nm in sorted(want, key=num):
    code = want[nm]
    refs = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == code:
                refs.setdefault(fp.GetReference(), []).append(p.GetNumber())
    print("%-7s %s" % (nm, "  ".join("%s.%s" % (r, ",".join(v))
                                     for r, v in sorted(refs.items()))))
