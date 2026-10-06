"""Every strip net's spine, and where it can be picked up from the west.

A net here is a bundle of segments.  What matters for re-driving it is the
long spine (the row line, or the column run) and the point on it that sits
closest to the empty corridor along the left edge.  Print both, plus every
vertex west of --west, which is where a new trace can legally land.

  python _tp_spine.py [--west 108] [NET ...]
"""
import re
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

argv = sys.argv[1:]
WEST = float(argv[argv.index("--west") + 1]) if "--west" in argv else 108.0
SEL = set(a for a in argv if not a.startswith("-") and not a.replace(".", "").isdigit())

WANT = re.compile(r"^(ROW\d+|CSEL\d+|IO\d+|DRV_CASC\d)$")

b = pcbnew.LoadBoard(PCB)

nets = {}
for t in b.GetTracks():
    nm = t.GetNetname().lstrip("/")
    if not WANT.match(nm) or isinstance(t, pcbnew.PCB_VIA):
        continue
    s, e = t.GetStart(), t.GetEnd()
    nets.setdefault(nm, []).append(
        (b.GetLayerName(t.GetLayer()), pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
         pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)))
for fp in b.GetFootprints():
    for p in fp.Pads():
        nm = p.GetNetname().lstrip("/")
        if not WANT.match(nm):
            continue
        q = p.GetPosition()
        nets.setdefault(nm, [])
        nets[nm].append(("PAD", pcbnew.ToMM(q.x), pcbnew.ToMM(q.y),
                         pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)))


def sortkey(n):
    if n.startswith("ROW"):
        return (0, int(n[3:]))
    if n.startswith("CSEL"):
        return (1, int(n[4:]))
    if n.startswith("IO"):
        return (2, int(n[2:]))
    return (3, n)


for nm in sorted(nets, key=sortkey):
    if SEL and nm not in SEL:
        continue
    ss = [s for s in nets[nm] if s[0] != "PAD"]
    pads = [s for s in nets[nm] if s[0] == "PAD"]
    hbest = vbest = None
    for lay, x0, y0, x1, y1 in ss:
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        ln = (dx * dx + dy * dy) ** 0.5
        if dx >= dy:
            if hbest is None or ln > hbest[0]:
                hbest = (ln, lay, min(x0, x1), max(x0, x1), (y0 + y1) / 2)
        else:
            if vbest is None or ln > vbest[0]:
                vbest = (ln, lay, (x0 + x1) / 2, min(y0, y1), max(y0, y1))
    west = sorted({(min(x0, x1), y0 if x0 <= x1 else y1)
                   for _, x0, y0, x1, y1 in ss
                   if min(x0, x1) < WEST},
                  key=lambda p: p[0])[:4]
    print("%-8s seg%d" % (nm, len(ss)))
    if hbest:
        print("     H spine %-3s x %6.1f..%6.1f  y %6.1f   (len %.0f)"
              % (hbest[1], hbest[2], hbest[3], hbest[4], hbest[0]))
    if vbest:
        print("     V spine %-3s x %6.1f  y %6.1f..%6.1f   (len %.0f)"
              % (vbest[1], vbest[2], vbest[3], vbest[4], vbest[0]))
    if west:
        print("     westmost vertices: %s"
              % "  ".join("(%.1f,%.1f)" % p for p in west))
    if pads:
        print("     pads: %s"
              % "  ".join("%.1f,%.1f" % (p[1], p[2]) for p in pads[:6]))
