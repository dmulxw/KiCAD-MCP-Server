"""Which net order routes everything, now that rip-up is in the loop?

Each pass costs ~15 s, so the cheapest reliable strategy is to try the plausible
orders and keep the best one rather than keep out-thinking the congestion.  Every
order runs through the same route_all(), so rip-up gets its chance in each.
"""
import importlib.util

import pcbnew

spec = importlib.util.spec_from_file_location(
    "route", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts\route.py")
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)

board = pcbnew.LoadBoard(route.BOARD)
_keep = route.clear_routing(board)

POWER = {"+5V", "VBAT", "VBAT_SW", "SW_NODE", "+3V3"}


def width(n):
    return route.WIDTHS.get(n, route.DEFAULT_W)


STRATEGIES = {
    "span asc (current)":  lambda n, s: (s,),
    "span desc":           lambda n, s: (-s,),
    "w desc span desc":    lambda n, s: (-width(n), -s),
    "w desc span asc":     lambda n, s: (-width(n), s),
    "w asc span asc":      lambda n, s: (width(n), s),
    "w asc span desc":     lambda n, s: (width(n), -s),
    "power first span asc": lambda n, s: (n not in POWER, s),
    "power last span asc":  lambda n, s: (n in POWER, s),
}

for label, key in STRATEGIES.items():
    r = route.Router(board)
    nets = [n for n in r.pads if n != "GND" and len(r.pads[n]) > 1]

    def span(net):
        pts = r.pads[net]
        return ((max(p[0] for p in pts) - min(p[0] for p in pts)) ** 2
                + (max(p[1] for p in pts) - min(p[1] for p in pts)) ** 2) ** 0.5

    nets.sort(key=lambda n: key(n, span(n)))
    failed = route.route_all(r, nets)
    print(f"{label:<22} {len(failed):>2} failed  {len(r.tracks):>4} tracks  "
          f"{len(r.vias):>3} vias   {', '.join(failed) if failed else '-- CLEAN --'}")
