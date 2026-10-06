"""What is the touch-panel's interface today, exactly?

Option B was chosen: the panel grows its own 595s driving the 12 nets its margins
already reach, and the other 19 nets come over the cable.  Every decision
downstream -- how far to widen, where the chips stand, which header pads are
free -- reads off the real board, so print it instead of quoting a summary.
"""
import collections
import sys

import pcbnew

P = sys.argv[1] if len(sys.argv) > 1 else "../touch-panel/touch-panel.kicad_pcb"
b = pcbnew.LoadBoard(P)
if b is None:
    sys.exit("LoadBoard(%s) returned None" % P)

edges = [d for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
xs, ys = [], []
for d in edges:
    for p in (d.GetStart(), d.GetEnd()):
        xs.append(pcbnew.ToMM(p.x))
        ys.append(pcbnew.ToMM(p.y))
print("board: %s" % P)
print("outline: x %.3f..%.3f  y %.3f..%.3f   (%.1f x %.1f)   %d edge items"
      % (min(xs), max(xs), min(ys), max(ys),
         max(xs) - min(xs), max(ys) - min(ys), len(edges)))

fps = list(b.GetFootprints())
print("footprints: %d" % len(fps))
print("by value:")
for v, c in collections.Counter(f.GetValue() for f in fps).most_common():
    print("   %5d  %s" % (c, v))

print("\nconnectors (ref begins with J):")
for fp in sorted(fps, key=lambda f: f.GetReference()):
    if not fp.GetReference().startswith("J"):
        continue
    p = fp.GetPosition()
    pads = list(fp.Pads())
    used = [q for q in pads if q.GetNetname()]
    print("\n  %-5s %-9s %-50s (%8.2f, %8.2f) rot %.0f"
          % (fp.GetReference(), fp.GetLayerName(),
             "%s:%s" % (fp.GetFPID().GetLibNickname(),
                        fp.GetFPID().GetLibItemName()),
             pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), fp.GetOrientationDegrees()))
    print("        %d pads, %d with a net" % (len(pads), len(used)))
    for q in sorted(pads, key=lambda z: (len(z.GetNumber()), z.GetNumber())):
        c = q.GetPosition()
        print("        pad %-4s (%8.2f, %8.2f)  %s"
              % (q.GetNumber(), pcbnew.ToMM(c.x), pcbnew.ToMM(c.y),
                 q.GetNetname() or "-- no net --"))

names = set()
for t in b.GetTracks():
    names.add(t.GetNetname())
for f in fps:
    for q in f.Pads():
        names.add(q.GetNetname())
names.discard("")
print("\nnets in use: %d" % len(names))
