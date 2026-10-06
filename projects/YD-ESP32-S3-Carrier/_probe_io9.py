"""Call route_net("IO9") directly and watch what it actually does.

_probe_taken.py showed taken=[True, False, False, False] for IO9 -- the loop
should run -- yet the real pass reported [OK] with 0 segments.  So either A*
found a path and emit() dropped it, or route_net returned before the loop.
This runs the call in isolation and prints the track count around it.

  python _probe_io9.py
"""
import sys

import pcbnew

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts")
import route

board = pcbnew.LoadBoard(route.BOARD)
router = route.Router(board)
route.absorb(board, router)

for net in ("IO9", "IO12", "IO10", "IO11"):
    before = sum(1 for t in router.tracks if t[0] == net)
    ok = router.route_net(net)
    after = sum(1 for t in router.tracks if t[0] == net)
    print("%-5s route_net=%-5s  fail_at=%-22s  tracks %d -> %d"
          % (net, ok, router.fail_at, before, after))

    # what does the taken[] array look like *now*, mid-pass?
    pads = router.pads.get(net, [])
    print("        pads: %s"
          % " ".join("(%.1f,%.1f)" % (p[0], p[1]) for p in pads))
