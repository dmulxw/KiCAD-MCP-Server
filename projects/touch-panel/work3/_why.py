"""Print the legality mask around a DRC pair, and what A* actually walked.

Hand-deriving a route from a list of neighbours is how you talk yourself into a
corridor that is 0.04mm too narrow.  The grid has the answer already; this
renders it.  '.' legal, '#' illegal, 'A'/'B' the pair's own copper, 'o' the
path A* returned.

    python _why.py <board> <net> [x0 y0 x1 y1]
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402
import emitlib as M                                                  # noqa: E402
import probe, replan                                                 # noqa: E402

S = 1e6
SRC = sys.argv[1]
NET = sys.argv[2]
LAY = M.LAYERS[int(os.environ.get("LAYER", "0"))]
BOX = [float(v) for v in sys.argv[3:7]] if len(sys.argv) >= 7 else [100.9, 125.4, 106.2, 130.0]

board = pcbnew.LoadBoard(SRC)
M.bind(board, st=0.1)
print("step=%.2f keep=%.3f pad_keep=%.3f" % (M.step, M.keep, M.pad_keep), flush=True)

allc = M.fresh()
obstacles = [it for it in allc if it.GetNetname() != NET]
grid = M.make_grid(obstacles)


def cells(it):
    if isinstance(it, pcbnew.PAD):
        c = replan.pad_cells(grid, it, M.LAYERS)
    else:
        c = list(replan.cells_of(grid, [it], M.LAYERS))
    ok = [x for x in c if grid.OK[x[0]][x[2], x[1]]]
    if ok:
        return ok
    out = []
    if isinstance(it, pcbnew.PAD):
        pts = [(it.GetPosition().x / S, it.GetPosition().y / S)]
    else:
        s, e = it.GetStart(), it.GetEnd()
        pts = [(s.x / S, s.y / S), (e.x / S, e.y / S)]
    for pt in pts:
        i, j = grid.ij(*pt)
        for l in M.LAYERS:
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    a, b = i + di, j + dj
                    if 0 <= a < grid.nx and 0 <= b < grid.ny and grid.OK[l][b, a]:
                        out.append((l, a, b))
    return list(dict.fromkeys(out))


# The pair, taken from the report so this agrees with stitch2 exactly.
d = json.load(open("_drc_r2.json", encoding="utf-8"))
byuuid = {}
for it in allc:
    try:
        byuuid[it.m_Uuid.AsString().replace("-", "").lower()] = it
    except Exception:
        pass
A = B = None
for ent in d.get("unconnected_items", []):
    its = ent.get("items", [])
    if len(its) != 2:
        continue
    a = byuuid.get(its[0]["uuid"].replace("-", "").lower())
    b = byuuid.get(its[1]["uuid"].replace("-", "").lower())
    if a is None or b is None or a.GetNetname() != NET or b.GetNetname() != NET:
        continue
    A, B = a, b
    break
if A is None:
    print("no DRC pair found for %s" % NET)
    sys.exit(1)


def ends(it):
    if isinstance(it, pcbnew.PAD):
        c = it.GetPosition()
        return [(c.x / S, c.y / S)]
    s, e = it.GetStart(), it.GetEnd()
    return [(s.x / S, s.y / S), (e.x / S, e.y / S)]


def name(it):
    if isinstance(it, pcbnew.PAD):
        return "pad"
    return "via" if isinstance(it, pcbnew.PCB_VIA) else "trk"


print("A = %s %s   B = %s %s" % (name(A), ends(A), name(B), ends(B)), flush=True)
st = cells(A)
gl = set(cells(B))
print("start cells %d, goal cells %d" % (len(st), len(gl)), flush=True)
for l, i, j in st[:6]:
    print("   start L%d (%.3f,%.3f) D=%.3f" % (l, grid.xy(i, j)[0], grid.xy(i, j)[1],
                                               grid.D[l][j, i]), flush=True)
for l, i, j in sorted(gl)[:6]:
    print("   goal  L%d (%.3f,%.3f) D=%.3f" % (l, grid.xy(i, j)[0], grid.xy(i, j)[1],
                                               grid.D[l][j, i]), flush=True)

path, cross, exp, closest = probe.astar(grid, st[:24], gl, 25.0, conflict=False)
print("astar -> %s  expanded %d  closest %.3fmm"
      % ("NONE" if path is None else "%d cells" % len(path), exp, closest[0] * M.step),
      flush=True)
if path is not None:
    ln = sum(((path[q][1] - path[q - 1][1]) ** 2 + (path[q][2] - path[q - 1][2]) ** 2) ** 0.5
             for q in range(1, len(path))) * M.step
    print("path length %.2fmm, %d points" % (ln, len(path)), flush=True)
    for p in path[:5] + path[-5:]:
        print("     L%d (%.3f,%.3f)" % (p[0], grid.xy(p[1], p[2])[0], grid.xy(p[1], p[2])[1]))
    print("   EVERY 10th POINT:", flush=True)
    for q in range(0, len(path), max(1, len(path) // 12)):
        p = path[q]
        print("     %4d L%d (%.3f,%.3f)" % (q, p[0], grid.xy(p[1], p[2])[0],
                                            grid.xy(p[1], p[2])[1]))

# The mask, with the pair's own copper and the path marked.
on_a = {(i, j) for _, i, j in cells(A)}
on_b = {(i, j) for _, i, j in cells(B)}
walk = {(p[1], p[2]) for p in path} if path else set()
i0, j0 = grid.ij(BOX[0], BOX[1])
i1, j1 = grid.ij(BOX[2], BOX[3])
print("\n%s on %s: x %.2f..%.2f  y %.2f..%.2f" % (SRC, LAY, BOX[0], BOX[2], BOX[1], BOX[3]))
hdr = "      " + "".join(str((i0 + k) % 10) for k in range(i1 - i0 + 1))
print(hdr)
for j in range(j0, j1 + 1):
    row = []
    for i in range(i0, i1 + 1):
        if (i, j) in walk:
            row.append("*")
        elif (i, j) in on_a:
            row.append("A")
        elif (i, j) in on_b:
            row.append("B")
        else:
            # VOK is orthogonal to OK: a cell can route but not take a via, or
            # take a via but not route.  Showing only the illegal-but-VOK case
            # hides the one that matters -- A* pays via_cost 25 to change layer,
            # so if a VOK cell were reachable inside a sealed pocket the search
            # would use it instead of a 146mm lap.  Both axes must be visible.
            can_route = grid.OK[LAY][j, i]
            can_via = bool(grid.VOK[j, i])
            if can_route and can_via:
                row.append("V")
            elif can_route:
                row.append(".")
            elif can_via:
                row.append("v")
            else:
                row.append("#")
    print("  %6.1f%s" % (grid.xy(0, j)[1], "".join(row)))
print("   x from %.3f, step %.2f" % (grid.xy(i0, 0)[0], M.step))
