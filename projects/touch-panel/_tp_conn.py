"""Where are the panel's connectors, and which of our nets do they already carry?"""
import sys

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)

WANT = set(["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
           + ["DRV_CASC1", "DRV_CASC2", "DRV_CASC3", "IO9", "IO10", "IO11",
              "IO12", "+3V3", "GND"])

rows = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if not ref[:1] in ("J", "P", "CN"):
        continue
    pads = list(fp.Pads())
    if len(pads) < 4:
        continue
    p = fp.GetPosition()
    nets = sorted({q.GetNetname() for q in pads if q.GetNetname()})
    hits = [n for n in nets if n in WANT]
    rows.append((ref, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), len(pads),
                 len(nets), hits))

print("%-6s %9s %9s %5s %5s  %s" % ("ref", "x", "y", "pads", "nets", "our nets present"))
for ref, x, y, np_, nn, hits in sorted(rows, key=lambda r: (r[2], r[1])):
    print("%-6s %9.2f %9.2f %5d %5d  %s"
          % (ref, x, y, np_, nn,
             (", ".join(hits[:10]) + (" ..." if len(hits) > 10 else "")) or "-"))

# Where does J1 (or the biggest connector) sit, and what is around it?
print("\n--- all footprints with ref J*, sorted by y ---")
for ref, x, y, np_, nn, hits in sorted(rows, key=lambda r: r[2]):
    print("  %-6s (%7.2f,%7.2f) pads=%d" % (ref, x, y, np_))
