"""Instrument route_net("IO9"): was emit() ever called, and what did taken[] say?

_probe_taken.py replicated the predicate by hand and got taken=[T,F,F,F], yet
route_net returns True with zero tracks and no "cannot reach pad".  That leaves
only two possibilities -- the loop never ran, or emit() ran and its output went
somewhere else.  Patching the two functions route.py already exposes tells them
apart.

  python _probe_why.py
"""
import sys

import pcbnew

sys.path.insert(0, r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts")
import route

calls = {"emit": 0, "reachable": 0, "astar": 0}

_emit = route.Router.emit
_reach = route.reachable
_astar = route.Router.astar


def emit(self, net, path, w, blocked, via_blocked, hw):
    calls["emit"] += 1
    print("      emit(%s, path of %d pt(s), w=%.2f)" % (net, len(path), w))
    return _emit(self, net, path, w, blocked, via_blocked, hw)


def reachable(mask, starts):
    got = _reach(mask, starts)
    calls["reachable"] += 1
    print("      reachable(starts=%d) -> %d cell(s)" % (len(starts), int(got.sum())))
    return got


def astar(self, blocked, via_blocked, starts, targets, crowd=None):
    calls["astar"] += 1
    print("      astar(starts=%d, target_cells=%d) ..." % (len(starts), int(targets.sum())))
    out = _astar(self, blocked, via_blocked, starts, targets, crowd)
    print("      astar -> %s" % ("None" if out is None else "%d pt(s)" % len(out)))
    return out


route.Router.emit = emit
route.reachable = reachable
route.Router.astar = astar

board = pcbnew.LoadBoard(route.BOARD)
router = route.Router(board)
route.absorb(board, router)

print("=== route_net('IO9') ===")
ok = router.route_net("IO9")
print("ok=%s  fail_at=%s  calls=%s" % (ok, router.fail_at, calls))
print("tracks for IO9: %d" % sum(1 for t in router.tracks if t[0] == "IO9"))
