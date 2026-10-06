"""What is the panel<->carrier interface today?

The user says the carrier needs no added sockets, which is right if the panel's
J1A/J1B mate with something that is already there.  But J8/J10 are the +595
additions -- so name every footprint on the pre-595 carrier, with its real
library name, and stop guessing about it.
"""
import sys

import pcbnew

for path in sys.argv[1:]:
    b = pcbnew.LoadBoard(path)
    if b is None:
        print("%s: LoadBoard returned None" % path)
        continue
    print("=== %s   %d footprints" % (path, len(b.GetFootprints())))
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        p = fp.GetPosition()
        print("   %-6s %-10s %-46s (%7.2f, %7.2f)  %s"
              % (fp.GetReference(), fp.GetLayerName(),
                 "%s:%s" % (fp.GetFPID().GetLibNickname(),
                            fp.GetFPID().GetLibItemName()),
                 pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), fp.GetValue()))
