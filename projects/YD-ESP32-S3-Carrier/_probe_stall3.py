"""Reproduce route_net's opening moves for the failing nets and say which pad is
unreachable, and why.

route_net() reports "cannot reach pad (x, y)" for the pad it is trying to hook up,
but the coordinates alone do not say which *layer* shut it out or which foreign
item did it.  This walks the same steps -- blocked_for(), pad_nodes() -- and
prints, per pad, how many of its grid nodes are usable on each layer, plus the
foreign copper sitting on the pad.

  python _probe_stall3.py
"""
import sys

import pcbnew

BASE = (r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier")
PRE = BASE + r"\_v90_pre.kicad_pcb"      # moved but unrouted: the cleanest read

sys.path.insert(0, BASE)
import scripts.route as R  # noqa: E402

board = pcbnew.LoadBoard(PRE)
if board is None:
    sys.exit("LoadBoard returned None for " + PRE)
router = R.Router(board)

# What was already on the board before this run started.
frozen = set(router.frozen)


def label(seg):
    return "FROZEN" if seg in frozen else "NEW"


for net in ("I2S_DO", "IO38", "I2S_DI", "I2S_WS", "IO17"):
    pads = router.pads.get(net, [])
    w = R.WIDTHS.get(net, R.DEFAULT_W)
    hw = w / 2.0
    blocked, _ = router.blocked_for(net, hw)
    print("=== %s: %d pad(s), w=%.2f ===" % (net, len(pads), w))
    for a, (px, py, nodes, layers) in enumerate(pads):
        lays = layers or (0, 1)
        free = {l: sum(1 for (i, j) in nodes if not blocked[l, i, j]) for l in (0, 1)}
        usable = [l for l in lays if free[l]]
        print("  pad %d at (%7.2f,%7.2f)  %3d nodes  free F/B = %3d/%3d  "
              "pad layers=%s  usable=%s"
              % (a, px, py, len(nodes), free[0], free[1],
                 "".join("FB"[l] for l in lays) or "-",
                 "".join("FB"[l] for l in usable) or "NONE"))
        if usable:
            continue
        # Pad fully shut.  Name the foreign copper on top of it.
        for (onet, layer, x1, y1, x2, y2, ww) in router.tracks + list(frozen):
            if onet == net:
                continue
            dx, dy = x2 - x1, y2 - y1
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx +
                                                      (py - y1) * dy) / L2))
            d = ((x1 + t * dx - px) ** 2 + (y1 + t * dy - py) ** 2) ** 0.5
            if d <= 0.85 + 0.15:            # inside the 1.70 mm pad, plus a hair
                print("        on the pad: %-6s %-5s (%7.3f,%7.3f)-(%7.3f,%7.3f)"
                      " w=%.2f  d=%.2f"
                      % (label((onet, layer, x1, y1, x2, y2, ww)), onet,
                         board.GetLayerName(layer), x1, y1, x2, y2, ww, d))
    print()
