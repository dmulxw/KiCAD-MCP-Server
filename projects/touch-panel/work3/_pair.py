"""Which connected component is each side of a DRC pair in, and how big is it?

stitch2 reports "NO PATH (closest X, N expanded)".  That one line cannot
distinguish the two ways a pair fails, and they need opposite fixes:

  * the search was sealed in a pocket          -> start/goal placement problem
  * the search roamed the whole board          -> capacity problem

Worse, `closest` cannot separate them either.  It is the min H over expanded
nodes (probe.py:353), and H on a goal-less layer is now ``best + via_cost``
after the via fix, so every cell on such a layer carries a floor of 25 (2.5mm)
no matter how far away it really is.  A reported "closest 2.50mm" may therefore
mean "we sat directly above the goal and could not drop onto it" or "we never
got near it at all".

So label the OK mask instead and name the component each side sits in.  The
8-connected flood is a superset of A*'s move set (A* additionally refuses a
diagonal whose two orthogonal neighbours are closed), so two cells in different
8-connected components of OK are definitely unreachable from each other, and a
component smaller than the expanded count proves the search was boxed in.

    python _pair.py <board> <drc.json> <net> [n]
"""
import json
import os
import sys
from collections import deque

sys.path.insert(0, os.getcwd())
import numpy as np                                                   # noqa: E402
import pcbnew                                                        # noqa: E402
import emitlib as M                                                  # noqa: E402
import probe, replan                                                 # noqa: E402

S = 1e6
SRC = sys.argv[1]
DRCJSON = sys.argv[2]
NET = sys.argv[3]
WANT = int(sys.argv[4]) if len(sys.argv) > 4 else 1

board = pcbnew.LoadBoard(SRC)
M.bind(board, st=0.1)

allc = M.fresh()
obstacles = [it for it in allc if it.GetNetname() != NET]
grid = M.make_grid(obstacles)
print("%s net=%s  nx=%d ny=%d step=%.2f keep=%.3f pad_keep=%.3f vek=%.3f"
      % (SRC, NET, grid.nx, grid.ny, M.step, M.keep, M.pad_keep, M.vek), flush=True)


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


def desc(it):
    if isinstance(it, pcbnew.PAD):
        return "pad"
    return "via" if isinstance(it, pcbnew.PCB_VIA) else "trk"


def laysof(it):
    return [int(l) for l in M.LAYERS if it.IsOnLayer(l)]


# ---- pick the pair, exactly as stitch2 builds it -------------------------
byuuid = {}
for it in allc:
    try:
        byuuid[it.m_Uuid.AsString().replace("-", "").lower()] = it
    except Exception:
        pass

d = json.load(open(DRCJSON, encoding="utf-8"))
want = []
for ent in d.get("unconnected_items", []):
    its = ent.get("items", [])
    if len(its) != 2:
        continue
    a = byuuid.get(its[0]["uuid"].replace("-", "").lower())
    b = byuuid.get(its[1]["uuid"].replace("-", "").lower())
    if a is None or b is None or a.GetNetname() != NET or b.GetNetname() != NET:
        continue
    want.append((a, b))
if not want:
    print("no DRC pair for %s" % NET)
    sys.exit(1)
A, B = want[min(WANT, len(want)) - 1]

print("A = %s %s layers=%s" % (desc(A), ends(A), laysof(A)), flush=True)
print("B = %s %s layers=%s" % (desc(B), ends(B), laysof(B)), flush=True)

st = cells(A)
gl = set(cells(B))
print("start %d cell(s), goal %d cell(s)" % (len(st), len(gl)), flush=True)

# ---- component flood -----------------------------------------------------
NB4 = ((-1, 0), (1, 0), (0, -1), (0, 1))


def flood(mask, seeds):
    ny, nx = mask.shape
    seen = np.zeros((ny, nx), bool)
    q = deque()
    for (j, i) in seeds:
        if mask[j, i] and not seen[j, i]:
            seen[j, i] = True
            q.append((j, i))
    while q:
        j, i = q.popleft()
        for dj, di in NB4:
            nj, ni = j + dj, i + di
            if 0 <= nj < ny and 0 <= ni < nx and mask[nj, ni] and not seen[nj, ni]:
                seen[nj, ni] = True
                q.append((nj, ni))
    return seen


for lay in M.LAYERS:
    s_seed = [(j, i) for l, i, j in st if l == lay]
    g_seed = [(j, i) for l, i, j in gl if l == lay]
    print("\n--- layer %d ---" % int(lay), flush=True)
    print("  start cells on this layer: %d   goal cells: %d" % (len(s_seed), len(g_seed)),
          flush=True)
    if not s_seed and not g_seed:
        continue
    reg_s = flood(grid.OK[lay], s_seed)
    reg_g = flood(grid.OK[lay], g_seed)
    ns, ng = int(reg_s.sum()), int(reg_g.sum())
    same = bool((reg_s & reg_g).any())
    print("  component of start: %d cell(s)   component of goal: %d cell(s)   %s"
          % (ns, ng, "SAME component" if same else "DIFFERENT components"), flush=True)
    # A via can only be taken where VOK holds.  If the start's own component
    # carries no VOK cell, this layer can never hand the route to the other one.
    nv_s = int((reg_s & grid.VOK).sum())
    nv_g = int((reg_g & grid.VOK).sum())
    print("  VOK cells in start component: %d   in goal component: %d" % (nv_s, nv_g),
          flush=True)
    if not same:
        # Where is the nearest goal cell from the start component, really?
        print("  -> the goal is in another island on this layer", flush=True)

# If start and goal never share a layer, the route MUST change layer.
sl = {l for l, i, j in st}
gll = {l for l, i, j in gl}
print("\nstart layers %s, goal layers %s -> %s"
      % ([int(v) for v in sorted(sl)], [int(v) for v in sorted(gll)],
         "must use a via" if not (sl & gll) else "shares a layer"), flush=True)

p, _, exp, closest = probe.astar(grid, st[:24], gl, 25.0, conflict=False)
print("astar -> %s  expanded %d  closest %.4fmm on layer %s"
      % ("NONE" if p is None else "%d cells/%d via" % (
          len(p), sum(1 for q in range(1, len(p)) if p[q][0] != p[q - 1][0])),
         exp, closest[0] * M.step,
         "?" if closest[1] is None else int(closest[1][0])), flush=True)
