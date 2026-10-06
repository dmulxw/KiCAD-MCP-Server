"""The netlist, per net: every pad on it, by reference.pad.

If ROW2's pad list already includes a J1A pin then the netlist says "row 2 goes
out to the header" and the copper stopping at (101.59,120.60) is an unfinished
route, not a finished one.  If ROW2 has no header pin, the 595 output is the
only thing that can drive it and the copper really does stop there on purpose.
The two cases call for opposite fixes, so this is worth reading off the board
rather than inferring from the copper.
"""
import sys
from collections import OrderedDict

import pcbnew

HERE = r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
sys.path.insert(0, HERE)
import _tp_route as R                                    # noqa: E402

WANT = (["ROW%d" % i for i in range(21)] + ["CSEL%d" % i for i in range(10)]
        + ["DRV_CASC1", "DRV_CASC2", "DRV_CASC3",
           "IO9", "IO10", "IO11", "IO12", "+3V3", "GND"])

board = pcbnew.LoadBoard(R.BOARD)

by_net = OrderedDict((n, []) for n in WANT)
for fp in board.GetFootprints():
    ref = fp.GetReference()
    for q in fp.Pads():
        n = q.GetNetname()
        if n in by_net:
            pos = q.GetPosition()
            by_net[n].append((ref, q.GetNumber(), pcbnew.ToMM(pos.x),
                              pcbnew.ToMM(pos.y)))


def key(t):
    m = t[0]
    return (0 if m in ("J1A", "J1B", "J1") else
            1 if m.startswith("U") else
            2 if m.startswith("R") else 3, m)


for n in WANT:
    pads = by_net[n]
    if not pads:
        print("%-10s  (no pads at all)" % n)
        continue
    refs = sorted({p[0] for p in pads})
    hdr = [p for p in pads if p[0] in ("J1A", "J1B", "J1")]
    fam = [r for r in refs if r.startswith("Q") or r.startswith("U")
           or r.startswith("R") or r.startswith("J")]
    print("%-10s %3d pad(s)  refs: %s"
          % (n, len(pads), ", ".join(fam[:12]) + (" ..." if len(fam) > 12 else "")))
    if hdr:
        print("           HEADER: %s"
              % ", ".join("%s.%s@(%.2f,%.2f)" % p for p in hdr))
    else:
        print("           HEADER: none")

# --- how many pads of each header pin are used ------------------------------
print("\n--- header pin usage ---")
for ref in ("J1A", "J1B", "J1"):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        continue
    used, spare = [], []
    for q in fp.Pads():
        n = q.GetNetname()
        (used if n else spare).append("%s=%s" % (q.GetNumber(), n or "-"))
    print("%-4s used[%d]: %s" % (ref, len(used), ", ".join(used)))
    print("     spare[%d]: %s" % (len(spare), ", ".join(spare)))
