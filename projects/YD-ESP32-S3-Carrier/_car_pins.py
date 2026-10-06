"""What could the carrier-side end of the panel cable plug into?

The user says the carrier takes no added socket, so the link has to land on
something that is already there.  Print every pad of every connector on the
pre-595 carrier with its net, so the spare capacity is a fact and not a guess.
"""
import sys

import pcbnew

WANT = {"J1", "J2", "J6", "J7", "J9", "J3", "J4", "J5"}

for path in sys.argv[1:]:
    b = pcbnew.LoadBoard(path)
    if b is None:
        print("%s: LoadBoard returned None" % path)
        continue
    print("=== %s" % path)
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if ref not in WANT:
            continue
        pads = list(fp.Pads())
        used = [p for p in pads if p.GetNetname()]
        print("\n  %-4s %-22s %d pads, %d with a net"
              % (ref, fp.GetValue(), len(pads), len(used)))
        for p in sorted(pads, key=lambda q: (len(q.GetNumber()),
                                             q.GetNumber())):
            c = p.GetPosition()
            print("     pad %-4s (%.2f, %.2f)  %s"
                  % (p.GetNumber(), pcbnew.ToMM(c.x), pcbnew.ToMM(c.y),
                     p.GetNetname() or "-- no net --"))
