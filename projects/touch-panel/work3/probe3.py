"""Was OK actually False at the cells astar returned?

Every shorting track endpoint in _r1.kicad_pcb sits exactly on a grid vertex, so
the path itself went there.  If D at those vertices is below keep, akar returned
an illegal path and the defect is in the search; if D is comfortably above keep,
the grid built during routing must have differed from the grid now -- i.e. some
copper the route crossed was not an obstacle when the route ran.

Rebuilds the same obstacle set route40.py used (everything not on this net) and
reads D/OWN at the offending vertices.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew
import emitlib as M
import edgeflood as E

S = 1e6
board = pcbnew.LoadBoard(os.environ.get("SRC", "_r1.kicad_pcb"))
M.bind(board, st=0.1)
print("step %.2f keep %.3f pad_keep %.3f egk %.3f vek %.3f"
      % (M.step, M.keep, M.pad_keep, M.egk, M.vek))

# vertex -> the nets whose copper the DRC says it shorts into
CASES = {
    "ROW9": [(100.45, 158.55), (100.55, 158.65), (100.55, 158.75),
             (100.95, 159.15)],
    "ROW1": [(100.95, 128.25), (102.35, 128.25), (102.55, 128.35),
             (102.65, 128.45)],
    "ROW2": [(102.85, 127.95), (102.95, 127.95), (103.05, 128.05)],
    "CSEL8": [(166.85, 244.85), (166.15, 244.85), (168.65, 233.35),
              (168.65, 233.45), (168.75, 233.55)],
}

for net, verts in CASES.items():
    obstacles = [it for it in M.fresh() if it.GetNetname() != net]
    g = M.make_grid(obstacles)
    print("=" * 78)
    print("%s   obstacles %d" % (net, len(obstacles)))
    for x, y in verts:
        i, j = g.ij(x, y)
        xa, ya = g.xy(i, j)
        d = g.D[pcbnew.F_Cu][j, i]
        ok = bool(g.OK[pcbnew.F_Cu][j, i])
        own = int(g.OWN[pcbnew.F_Cu][j, i])
        desc = "INF/-"
        if own >= 0:
            it = obstacles[own]
            desc = ("%s %s" % (type(it).__name__,
                               it.GetNetname() if hasattr(it, "GetNetname")
                               else "?"))
        tag = "" if (abs(xa - x) < 1e-6 and abs(ya - y) < 1e-6) else "  *** SNAPPED"
        print("  (%8.3f,%8.3f) cell(%4d,%4d)  D=%7.4f  OK=%-5s  keep=%.2f  "
              "nearest=%s%s" % (x, y, i, j, float(d), ok, M.keep, desc, tag))
