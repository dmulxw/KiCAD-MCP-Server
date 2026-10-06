"""What is the touch-panel's interface right now, and what is on the free strip?

The 595s would go on the right-hand free strip (x 167..181, y 100..179), which is
the 14.25 x 79.25 mm hole _tp_free.py found.  Whether that is useful depends on two
things it did not answer: what connector the panel presents today (40 pins of
J1A/J1B, or still the old FPC), and what copper already occupies that strip -- a
free *courtyard* is not a free routing area, and the 595 outputs have to reach the
ROW/CSEL distribution.
"""
import collections

import numpy as np
import pcbnew

b = pcbnew.LoadBoard("../touch-panel/touch-panel.kicad_pcb")

byref = {}
for fp in b.GetFootprints():
    byref.setdefault(fp.GetReference().rstrip("0123456789") or fp.GetReference(), 0)
    byref[fp.GetReference().rstrip("0123456789") or fp.GetReference()] += 1
print("footprint prefixes:", " ".join("%s=%d" % kv for kv in sorted(byref.items())))

print("\nconnectors / anything not a passives-trio or an AO3400:")
for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    ref = fp.GetReference()
    pre = ref.rstrip("0123456789")
    if pre in ("Q", "R", "C"):
        continue
    p = fp.GetPosition()
    print("  %-6s %-46s at %.2f, %.2f"
          % (ref, fp.GetFPID().GetLibItemName(), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))

print("\nzones:")
for z in b.Zones():
    print("  %-10s layers %s  filled %s"
          % (z.GetNetname(), [b.GetLayerName(l) for l in z.GetLayerSet().Seq()],
             z.IsFilled()))

# Copper inside the right strip, per layer, as a fraction of the area.
track = collections.Counter()
xs, ys = [90.0, 181.0], [100.0, 250.0]
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    mx, my = (pcbnew.ToMM(s.x) + pcbnew.ToMM(e.x)) / 2, (pcbnew.ToMM(s.y) + pcbnew.ToMM(e.y)) / 2
    if 166.8 <= mx <= 181.0:
        track[b.GetLayerName(t.GetLayer())] += pcbnew.ToMM(t.GetLength())
print("\nright strip x 166.8..181.0 -- existing track length by layer:")
for k, v in sorted(track.items()):
    print("  %-8s %8.1f mm" % (k, v))

pads = sum(1 for fp in b.GetFootprints()
           if 166.8 <= pcbnew.ToMM(fp.GetPosition().x) <= 181.0)
print("  footprints in strip: %d" % pads)
