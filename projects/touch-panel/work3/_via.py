"""Does A* actually use a via when one is available?

WHY THIS EXISTS
---------------
_why.py showed the ROW3 pair's fragments are 3.18mm apart, that A's pocket is
full of VOK cells (route-legal AND via-legal) right on the stub, and that B.Cu
under ROW2's wall is legal the whole way across -- the wall is F.Cu-only.  Yet
astar returned a 146.41mm lap over the top of the board with ZERO vias, when
two vias cost 25 each and the whole crossing is ~2mm of travel.

So either VOK is false where the mask says true, or the via transition in
probe.astar never fires.  Reading the mask cannot separate those two; this can.
It asks astar for a path to a goal placed ON B.Cu, which is only reachable
through a via, and reports what came back.

    python _via.py <board> <net> [x y]
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
board = pcbnew.LoadBoard(SRC)
M.bind(board, st=0.1)

print("M.LAYERS = %s" % ([int(l) for l in M.LAYERS],), flush=True)

allc = M.fresh()
obstacles = [it for it in allc if it.GetNetname() != NET]
grid = M.make_grid(obstacles)
print("grid.layers = %s  n=%d" % ([int(l) for l in grid.layers], grid.n), flush=True)


def cells(it):
    if isinstance(it, pcbnew.PAD):
        c = replan.pad_cells(grid, it, M.LAYERS)
    else:
        c = list(replan.cells_of(grid, [it], M.LAYERS))
    ok = [x for x in c if grid.OK[x[0]][x[2], x[1]]]
    if ok:
        return ok
    out = []
    for pt in ends(it):
        i, j = grid.ij(*pt)
        for l in M.LAYERS:
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    a, b = i + di, j + dj
                    if 0 <= a < grid.nx and 0 <= b < grid.ny and grid.OK[l][b, a]:
                        out.append((l, a, b))
    return list(dict.fromkeys(out))


def ends(it):
    if isinstance(it, pcbnew.PAD):
        c = it.GetPosition()
        return [(c.x / S, c.y / S)]
    s, e = it.GetStart(), it.GetEnd()
    return [(s.x / S, s.y / S), (e.x / S, e.y / S)]


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

st = cells(A)
print("\nA ends %s -> %d start cell(s)" % (ends(A), len(st)), flush=True)
for l, i, j in st:
    x, y = grid.xy(i, j)
    print("   L%d (%7.3f,%7.3f)  OK=%s VOK=%s  D=%s"
          % (l, x, y, bool(grid.OK[l][j, i]), bool(grid.VOK[j, i]),
             {int(k): round(float(grid.D[k][j, i]), 3) for k in M.LAYERS}), flush=True)

# 1. Can we reach B at all (the search stitch2 runs)?
gl = set(cells(B))
p, _, exp, cl = probe.astar(grid, st[:24], gl, 25.0, conflict=False)
if p is None:
    print("\n1. to B: NO PATH (%d expanded)" % exp, flush=True)
else:
    lv = sorted({q[0] for q in p})
    print("\n1. to B: %d cells, %d expanded, layers used %s"
          % (len(p), exp, [int(v) for v in lv]), flush=True)

# 2. A goal on the OTHER layer, reachable only through a via.
#    If this also comes back NO PATH, the via transition is dead and every
#    long bridge in the stitch run is an artefact of that, not of geometry.
B_LAY = [l for l in M.LAYERS if l != M.LAYERS[0]][0]
i, j = grid.ij(101.4, 128.6)
gg = set()
for dj in range(-4, 5):
    for di in range(-4, 5):
        a, b = i + di, j + dj
        if (0 <= a < grid.nx and 0 <= b < grid.ny
                and grid.OK[B_LAY][b, a]):
            gg.add((B_LAY, a, b))
print("\n2. goal ON L%d near (101.4,128.6): %d cell(s)" % (int(B_LAY), len(gg)), flush=True)
p2, _, exp2, cl2 = probe.astar(grid, st[:24], gg, 25.0, conflict=False)
if p2 is None:
    print("   NO PATH (%d expanded, closest %.2fmm) -- via transition never fired"
          % (exp2, cl2[0] * M.step), flush=True)
else:
    print("   %d cells, %d expanded, layers used %s"
          % (len(p2), exp2, [int(v) for v in sorted({q[0] for q in p2})]), flush=True)
    print("   path:", flush=True)
    for q in p2:
        print("     L%d (%.3f,%.3f) VOK=%s" % (q[0], grid.xy(q[1], q[2])[0],
                                               grid.xy(q[1], q[2])[1],
                                               bool(grid.VOK[q[2], q[1]])))

# 3. Same, with the via made nearly free.  If the answer changes, cost is the
#    discriminator; if it does not, the transition is not being offered at all.
p3, _, exp3, _ = probe.astar(grid, st[:24], gg, 0.1, conflict=False)
print("\n3. via_cost=0.1 -> %s (%d expanded)"
      % ("NONE" if p3 is None else "%d cells" % len(p3), exp3), flush=True)

# 4. Bisect the hand-derived crossing, one waypoint at a time.  The crossing is
#    A -> via -> B.Cu south -> via -> F.Cu east -> B.  Asking for a single cell
#    at a time says WHICH leg is fiction; the whole-route search only says that
#    one of them is.
print("\n4. one waypoint at a time (each is a single goal cell):", flush=True)
F = M.LAYERS[0]
for tag, lay, wx, wy in (
        ("B.Cu mid   ", B_LAY, 101.45, 128.5),
        ("B.Cu deep  ", B_LAY, 101.45, 129.0),
        ("F.Cu back  ", F,     101.45, 128.5),
        ("F.Cu east  ", F,     102.90, 128.5),
        ("F.Cu nearB ", F,     103.85, 129.25),
        ("F.Cu B-w  ", F,      103.85, 128.6),
):
    i2, j2 = grid.ij(wx, wy)
    ok = bool(grid.OK[lay][j2, i2])
    # Snap to the nearest legal cell on that layer: a waypoint is a place I want
    # the route to pass, not necessarily a cell the grid happens to accept.
    if not ok:
        for r in range(1, 6):
            hit = None
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    a, b = i2 + di, j2 + dj
                    if (0 <= a < grid.nx and 0 <= b < grid.ny
                            and grid.OK[lay][b, a]):
                        hit = (a, b)
                        break
                if hit:
                    break
            if hit:
                i2, j2 = hit
                ok = True
                break
    if not ok:
        print("   %s L%d (%.2f,%.2f): no legal cell within 0.5mm" % (tag, int(lay), wx, wy),
              flush=True)
        continue
    single = {(lay, i2, j2)}
    p4, _, e4, c4 = probe.astar(grid, st[:24], single, 25.0, conflict=False)
    vias = 0
    if p4 is not None:
        vias = sum(1 for q in range(1, len(p4)) if p4[q][0] != p4[q - 1][0])
    print("   %s L%d target (%.3f,%.3f) snapped(%.3f,%.3f) D=%s -> %s"
          % (tag, int(lay), wx, wy, grid.xy(i2, j2)[0], grid.xy(i2, j2)[1],
             {int(k): round(float(grid.D[k][j2, i2]), 3) for k in M.LAYERS},
             "NONE (%d exp, closest %.2fmm)" % (e4, c4[0] * M.step) if p4 is None
             else "%d cells, %d via(s)" % (len(p4), vias)), flush=True)
