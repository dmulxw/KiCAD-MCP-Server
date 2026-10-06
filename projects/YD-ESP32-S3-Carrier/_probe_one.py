"""Route ONE net on a bare board and say exactly where it gives up.

route_all() reports a straggler as 0 segments, which is ambiguous: it can mean
A* never found a path, or that the net routed and was later ripped out.  On a
board whose whole lower strip measures empty, the difference is the entire
question -- one is congestion, the other is a bug in the router.

So: bare the board, route the net alone, print the outcome and the stall point.

    python _probe_one.py ROW6 CSEL0 ROW19
"""
import sys, os

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import numpy as np
import pcbnew

import route as R


def main():
    board = pcbnew.LoadBoard(R.BOARD)
    router = R.Router(board)
    R.absorb(board, router)

    todo = [n for n in router.pads if n != "GND" and len(router.pads[n]) > 1]
    R.rip(router, set(todo))          # bare board: our copper gone, frozen stays
    print("bare: %d track(s) left in router, %d frozen\n"
          % (len(router.tracks), len(router.frozen)), flush=True)

    for net in sys.argv[1:]:
        router.tracks, router.vias = [], []
        pads = router.pads.get(net, [])
        w = R.WIDTHS.get(net, R.DEFAULT_W)
        ok = router.route_net(net)
        got = [t for t in router.tracks if t[0] == net]
        nv = [v for v in router.vias if v[0] == net]
        print("%-8s pads=%d w=%.2f  ->  %s   %d seg(s) %d via(s)  fail_at=%s"
              % (net, len(pads), w, "OK" if ok else "FAIL",
                 len(got), len(nv), router.fail_at), flush=True)
        for (_, l, x1, y1, x2, y2, ww) in got[:4]:
            print("      %s (%.2f,%.2f)-(%.2f,%.2f) w=%.2f"
                  % ("F.Cu" if l == 0 else "B.Cu", x1, y1, x2, y2, ww), flush=True)
        for (i, (px, py, nodes, layers)) in enumerate(pads):
            # how many of this pad's own grid nodes are blocked by something else
            m, _v = router.blocked_for(net, w / 2.0)
            free = sum(1 for (ii, jj) in nodes for l in (layers or (0, 1))
                       if not m[l, ii, jj])
            print("      pad%d %-5s (%.2f,%.2f) %d node(s), %d free"
                  % (i, "", px, py, len(nodes) * len(layers or (0, 1)), free),
                  flush=True)


if __name__ == "__main__":
    main()
