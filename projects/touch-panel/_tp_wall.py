"""Render the router's own blocked mask for one net over a window."""
import importlib.util, sys, numpy as np, pcbnew
spec = importlib.util.spec_from_file_location("R", "_tp_route.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

NET = sys.argv[1]
x1, y1, x2, y2 = [float(v) for v in sys.argv[2].split(",")]
cell = float(sys.argv[3]) if len(sys.argv) > 3 else 0.20

board = pcbnew.LoadBoard(R.BOARD)
rt = R.Router(board)
R.absorb(board, rt)
w = R.WIDTHS.get(NET, R.DEFAULT_W)
blocked, via_blocked = rt.blocked_for(NET, w / 2.0)

i0 = int(round((x1 - R.OX) / R.GRID)); i1 = int(round((x2 - R.OX) / R.GRID))
j0 = int(round((y1 - R.OY) / R.GRID)); j1 = int(round((y2 - R.OY) / R.GRID))
step = max(1, int(round(cell / R.GRID)))

print("%s  blocked mask, x %.1f..%.1f y %.1f..%.1f   '#'=blocked 'v'=via-only-blocked '.'=free" % (NET, x1, y1, x2, y2))
print("       " + "".join(("%-10s" % ("%.1f" % R.mx(i))) if (i - i0) % (10 * step) == 0 else ""
                        for i in range(i0, i1 + 1, step)))
for j in range(j0, j1 + 1, step):
    row = []
    for i in range(i0, i1 + 1, step):
        b = blocked[0, i, j] and blocked[1, i, j]
        bf = blocked[0, i, j]; bb = blocked[1, i, j]
        v = via_blocked[0, i, j] and via_blocked[1, i, j]
        if not bf and not bb:
            ch = "."
        elif bf and bb:
            ch = "v" if v else "#"
        else:
            ch = "F" if bf else "B"
        row.append(ch)
    print("%6.1f " % R.my(j) + "".join(row))
