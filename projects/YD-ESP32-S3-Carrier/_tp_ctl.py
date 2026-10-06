"""Option B's real question: what can reach the chips, and what can reach the cable?

The 595 plan only pays off if the chips can be fed -- and fed from somewhere the
carrier can also reach.  So print the cable side first: which connector carries
which net, and which of those nets' copper actually touches the margin free space
a chip can stand in.  Every claim about "19 signals over the cable" rests on J1
being able to carry them, so read J1 out of the board instead of trusting a note.
"""
import sys

import pcbnew

b = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")
if b is None:
    sys.exit("LoadBoard returned None")

for ref in sorted({f.GetReference() for f in b.GetFootprints()
                   if f.GetReference().startswith("J")}):
    fp = b.FindFootprintByReference(ref)
    pads = list(fp.Pads())
    nets = {}
    for p in pads:
        n = p.GetNetname()
        if n:
            nets.setdefault(n, []).append(p.GetNumber())
    pos = fp.GetPosition()
    print("%-5s %-42s (%7.2f,%7.2f)  %2d pads  %2d used"
          % (ref, fp.GetFPID().GetLibItemName(), pcbnew.ToMM(pos.x),
             pcbnew.ToMM(pos.y), len(pads), len(nets)))
    print("      " + " ".join("%s=%s" % (n, ",".join(v))
                              for n, v in sorted(nets.items())))

print("\ntracks by net (top 12 by segment count):")
import collections
c = collections.Counter(t.GetNetname() for t in b.GetTracks() if t.GetNetname())
print("  " + " ".join("%s:%d" % kv for kv in c.most_common(12)))
