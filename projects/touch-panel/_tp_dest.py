"""Where do the 595 outputs have to reach, and what else is in the way?

The migration put four shift registers in a column at x=95 and left 39 nets
with bare pads.  Routing them is only a question of what is on the receiving
end, so this lists every connector's pin-to-net map and every footprint's
position, and then measures the free copper between the 595 output column and
whatever the row and column buses actually land on.

  python _tp_dest.py
"""
import collections

import pcbnew

BOARD = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel\touch-panel.kicad_pcb"
TO = pcbnew.ToMM

board = pcbnew.LoadBoard(BOARD)
bb = board.GetBoardEdgesBoundingBox()
print("board: (%.1f,%.1f)-(%.1f,%.1f)"
      % (TO(bb.GetLeft()), TO(bb.GetTop()), TO(bb.GetRight()), TO(bb.GetBottom())))

print("\n=== all footprints ===")
for f in sorted(board.GetFootprints(), key=lambda f: (f.GetPosition().y, f.GetPosition().x)):
    o = f.GetPosition()
    pads = list(f.Pads())
    print("  %-6s %-42s (%7.2f,%7.2f) rot=%-3.0f %2d pad(s)"
          % (f.GetReference(), str(f.GetFPID().GetLibItemName())[:42],
             TO(o.x), TO(o.y), f.GetOrientationDegrees(), len(pads)))

for ref in ("TP1", "J1", "J1A", "J2", "J3", "J4", "J5"):
    f = board.FindFootprintByReference(ref)
    if f is None:
        continue
    print("\n=== %s pin -> net ===" % ref)
    rows = []
    for p in f.Pads():
        o = p.GetPosition()
        rows.append((TO(o.x), TO(o.y), str(p.GetNumber()), p.GetNetname(),
                     board.GetLayerName(p.GetLayer())))
    for (x, y, num, net, lay) in sorted(rows, key=lambda r: (r[0], r[1])):
        print("   pad %-4s (%8.2f,%8.2f) %-6s %s" % (num, x, y, lay, net))

print("\n=== net -> every pad on it, for the 39 open nets ===")
allpads = collections.defaultdict(list)
for f in board.GetFootprints():
    for p in f.Pads():
        n = p.GetNetname()
        if n:
            o = p.GetPosition()
            allpads[n].append((f.GetReference(), str(p.GetNumber()), TO(o.x), TO(o.y)))
open_nets = []
for n in sorted(allpads):
    if n.startswith("ROW") or n.startswith("CSEL") or n in (
            "+3V3", "IO9", "IO10", "IO11", "IO12", "DRV_CASC1", "DRV_CASC2", "DRV_CASC3"):
        open_nets.append(n)
for n in open_nets:
    v = allpads[n]
    print("  %-9s %2d pad(s): %s" % (n, len(v),
          "  ".join("%s.%s(%.1f,%.1f)" % e for e in v[:8])))
