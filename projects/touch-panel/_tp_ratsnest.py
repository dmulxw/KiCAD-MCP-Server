"""Calibrate Freerouting's "unrouted" number against KiCad's own connectivity.

Freerouting reported 493 unrouted items at the start of auto-routing and is now
down to 120.  But DRC reports only 59 unconnected_items for the same board, and
those are PAIRS of disconnected copper, not one per missing link.  Until the two
units are reconciled, "120" cannot be compared with "59" and the whole run
cannot be judged.

KiCad's connectivity engine exposes the same ratsnest Freerouting is working
from, so this prints:
  * the unrouted (airwire) link count per net, summed,
  * the number of nets with any unrouted link,
  * the top nets by unrouted link count,
for the exported board, so 493 (or not) becomes a KiCad-side number too.

  python _tp_ratsnest.py [board.kicad_pcb]
"""
import sys
from collections import Counter

import pcbnew

path = sys.argv[1] if len(sys.argv) > 1 else "touch-panel.kicad_pcb"
board = pcbnew.LoadBoard(path)

conn = board.GetConnectivity()
conn.Build(board)

# The ratsnest API has moved around between releases; try each spelling.
links = None
for getter in ("GetUnconnectedEdges", "GetRatsnestEdges", "GetUnconnectedItems"):
    fn = getattr(conn, getter, None)
    if fn is None:
        continue
    try:
        links = fn()
        print("used conn.%s()" % getter)
        break
    except Exception as e:
        print("conn.%s() failed: %s" % (getter, e))

if links is None:
    n = getattr(conn, "GetUnconnectedCount", None)
    if n is None:
        print("no ratsnest accessor found on %s" % type(conn))
        sys.exit(0)
    ok = False
    for arg in (False, 0):
        try:
            print("conn.GetUnconnectedCount(%r) = %d" % (arg, n(arg)))
            ok = True
            break
        except TypeError:
            pass
    if not ok:
        print("GetUnconnectedCount takes %d arg(s)"
              % (n.__doc__ or "unknown",))
    sys.exit(0)

per = Counter()
total = 0
for e in links:
    try:
        net = str(e.GetNetname())
    except Exception:
        try:
            net = str(board.FindNet(e.GetNetCode()).GetNetname())
        except Exception:
            net = "?"
    per[net] += 1
    total += 1

print("board: %s" % path)
print("unrouted airwire links total : %d" % total)
print("nets with >=1 unrouted link : %d" % len(per))
print("\ntop nets by unrouted links:")
for n, c in per.most_common(30):
    print("   %-10s %3d" % (n, c))
