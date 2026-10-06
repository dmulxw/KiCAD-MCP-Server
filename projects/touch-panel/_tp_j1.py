"""What does J1 carry now, and where does its copper go?

The matrix nets stay on the board after the migration -- only their driver
moves.  So the copper that must be deleted is not "every ROW* track" but
specifically the feeder from J1.  This dumps J1's pads with their nets, then
for each of those nets the copper that touches J1's pad, so the feeder can be
separated from the row line it feeds.

  python _tp_j1.py [REF ...]
"""
import sys

import pcbnew

PCB = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")

REFS = [a for a in sys.argv[1:] if not a.startswith("-")] or ["J1"]

b = pcbnew.LoadBoard(PCB)

# every track, indexed by net, with uuid -> object
tracks = list(b.GetTracks())
by_net = {}
for t in tracks:
    by_net.setdefault(t.GetNetname().lstrip("/"), []).append(t)

for ref in REFS:
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        print("!! no footprint %s" % ref)
        continue
    o = fp.GetPosition()
    print("=== %s  %s  at (%.2f, %.2f) rot %.0f  layer %s"
          % (ref, fp.GetFPID().GetLibItemName() or "<empty fpid>",
             pcbnew.ToMM(o.x), pcbnew.ToMM(o.y),
             fp.GetOrientationDegrees(), b.GetLayerName(fp.GetLayer())))
    pads = []
    for p in fp.Pads():
        q = p.GetPosition()
        pads.append((p.GetNumber(), pcbnew.ToMM(q.x), pcbnew.ToMM(q.y),
                     p.GetNetname().lstrip("/")))
    for num, x, y, nm in pads:
        ts = by_net.get(nm, [])
        # tracks with an endpoint within 0.05 mm of the pad
        touch = 0
        for t in ts:
            if isinstance(t, pcbnew.PCB_VIA):
                continue
            for e in (t.GetStart(), t.GetEnd()):
                if abs(pcbnew.ToMM(e.x) - x) < 0.05 and \
                   abs(pcbnew.ToMM(e.y) - y) < 0.05:
                    touch += 1
                    break
        print("   pad %-4s (%7.2f, %7.2f)  %-10s  net has %4d track(s), %d touch"
              % (num, x, y, nm, len(ts), touch))
