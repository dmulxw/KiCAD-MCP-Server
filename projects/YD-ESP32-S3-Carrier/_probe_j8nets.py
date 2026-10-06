"""What do J8/J10 actually carry, and where do ROW*/CSEL* live on this board?"""
import sys

import pcbnew

BOARD = sys.argv[1] if len(sys.argv) > 1 else (
    r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
    r"\YD-ESP32-S3-Carrier.kicad_pcb")
TO = pcbnew.ToMM

board = pcbnew.LoadBoard(BOARD)
if board is None:
    sys.exit("LoadBoard returned None for " + BOARD)

for ref in ("J8", "J10", "J1", "J2"):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        print(ref, "missing")
        continue
    ps = sorted(fp.Pads(), key=lambda p: int(str(p.GetNumber())))
    print("=== %s (%s) ===" % (ref, str(fp.GetValue())))
    row = []
    for p in ps:
        n = str(p.GetNumber())
        net = str(p.GetNetname()) or "-"
        row.append("%s:%s" % (n, net))
    for k in range(0, len(row), 6):
        print("   " + "  ".join("%-14s" % c for c in row[k:k + 6]))
    print()

print("=== nets named ROW*/CSEL*/DRV_CASC* : pad count ===")
from collections import Counter
c = Counter()
owner = {}
for f in board.GetFootprints():
    for p in f.Pads():
        n = str(p.GetNetname())
        if n.startswith("ROW") or n.startswith("CSEL") or n.startswith("DRV_CASC"):
            c[n] += 1
            owner.setdefault(n, set()).add(str(f.GetReference()))
for n in sorted(c, key=lambda s: (s[:4], int("".join(ch for ch in s if ch.isdigit()) or 0))):
    print("  %-10s %2d pad(s)  %s" % (n, c[n], ",".join(sorted(owner[n]))))
print("  total %d such nets" % len(c))
