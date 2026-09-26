"""Bridge exactly the pairs DRC names, one bridge per pair.

stitch.py infers the fragments from a geometric island model and then bridges
every fragment it thinks is an orphan.  That model has to guess, and guessing
costs twice: where it errs strict it emits redundant bridges (they consume the
corridor the real bridges need), and where it errs loose it skips a pair DRC
still wants.  Measured on _r2 -> _s1: 59 bridges emitted, unconnected only fell
82 -> 24 with 69 dangling tracks, so most of that copper bought nothing.

DRC already knows.  Its `unconnected_items` entries name the two items that
failed to meet, by uuid, and a uuid is an exact handle on the board item.  So:
one bridge per entry, from item A to item B, and nothing else.  On _r2 that is
82 entries and 82 bridges, each attaching at both ends to the exact copper that
was disconnected.

    python stitch2.py --dry
    python stitch2.py --out _t1.kicad_pcb
"""
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402
import emitlib as M                                                  # noqa: E402
import probe, replan                                                 # noqa: E402

S = 1e6
LAYERS = M.LAYERS

SRC = os.environ.get("SRC", "_r2.kicad_pcb")
OUT = os.environ.get("OUT", "_t1.kicad_pcb")
DRC = os.environ.get("DRC", "_drc_r2.json")
ONLY = []
if "--nets" in sys.argv:
    ONLY = sys.argv[sys.argv.index("--nets") + 1:]
DRRY = "--dry" in sys.argv
LIMIT = 0
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])


def uuid_of(it):
    """The uuid as DRC prints it.

    There is no GetUuid() in this build and str(m_Uuid) is the SWIG proxy, not
    the id: KIID.AsString() is the only thing that yields KiCad's canonical
    8-4-4-4-12 form, which is what the DRC report carries.
    """
    return it.m_Uuid.AsString().replace("-", "").lower()


# --------------------------------------------------------------- the pairs
d = json.load(open(DRC, encoding="utf-8"))
board = pcbnew.LoadBoard(SRC)
M.bind(board, st=0.1)

byuuid = {}
for it in M.fresh():
    try:
        byuuid[uuid_of(it)] = it
    except Exception:
        pass

def uuid_of_str(u):
    return u.replace("-", "").lower()


pairs = []
missing = 0
for ent in d.get("unconnected_items", []):
    its = ent.get("items", [])
    if len(its) != 2:
        missing += 1
        continue
    a = byuuid.get(uuid_of_str(its[0]["uuid"]))
    b = byuuid.get(uuid_of_str(its[1]["uuid"]))
    if a is None or b is None:
        missing += 1
        continue
    net = a.GetNetname()
    if b.GetNetname() != net:
        missing += 1
        continue
    if ONLY and net not in ONLY:
        continue
    pairs.append((net, a, b, its[0].get("pos", {}), its[1].get("pos", {})))

print("%s: %d named pair(s) resolved (%d unresolved), %d target net(s)"
      % (DRC, len(pairs), missing, len({p[0] for p in pairs})), flush=True)
print("%s  step=%.2f keep=%.3f pad_keep=%.3f egk=%.3f vek=%.3f"
      % (SRC, M.step, M.keep, M.pad_keep, M.egk, M.vek), flush=True)
if not pairs:
    sys.exit(0)


def box_of(it):
    bb = it.GetBoundingBox()
    return (bb.GetLeft() / S, bb.GetTop() / S, bb.GetRight() / S, bb.GetBottom() / S)


def gap(p, q):
    dx = max(p[0] - q[2], q[0] - p[2], 0.0)
    dy = max(p[1] - q[3], q[1] - p[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


# Shortest gap first: a pair 0.05mm apart costs one segment and closes the hole
# before the long bridges have spent the corridor.
pairs.sort(key=lambda p: gap(box_of(p[1]), box_of(p[2])))
if LIMIT:
    pairs = pairs[:LIMIT]
print("shortest named pair: %.3fmm; longest: %.3fmm"
      % (gap(box_of(pairs[0][1]), box_of(pairs[0][2])),
         gap(box_of(pairs[-1][1]), box_of(pairs[-1][2]))), flush=True)


def cells(grid, it):
    """Legal cells on this one item's copper."""
    if isinstance(it, pcbnew.PAD):
        c = replan.pad_cells(grid, it, LAYERS)
    else:
        c = list(replan.cells_of(grid, [it], LAYERS))
    ok = [x for x in c if grid.OK[x[0]][x[2], x[1]]]
    if ok:
        return ok
    # Copper too thin to cover a legal cell (a 0.0636mm stub cannot): ring the
    # endpoints with the nearest legal cells instead.  attach_pt then grinds
    # the emitted segment back onto the stub's centreline.
    out = []
    for pt in endpoints(it):
        i, j = grid.ij(pt[0], pt[1])
        for l in LAYERS:
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    a, b = i + di, j + dj
                    if (0 <= a < grid.nx and 0 <= b < grid.ny
                            and grid.OK[l][b, a]):
                        out.append((l, a, b))
    return list(dict.fromkeys(out))


def endpoints(it):
    """The points attach_pt will aim at, in mm."""
    if isinstance(it, pcbnew.PAD):
        return [(it.GetPosition().x / S, it.GetPosition().y / S)]
    s, e = it.GetStart(), it.GetEnd()
    return [(s.x / S, s.y / S), (e.x / S, e.y / S)]


def desc(it):
    if isinstance(it, pcbnew.PAD):
        return "pad"
    if isinstance(it, pcbnew.PCB_VIA):
        return "via"
    return "trk"


total_ok = total_no = 0
total_len = 0.0
worst = (0.0, None)
t0 = time.time()
for n, (net, A, B, pa, pb) in enumerate(pairs, 1):
    allc = M.fresh()
    obstacles = [it for it in allc if it.GetNetname() != net]
    grid = M.make_grid(obstacles)
    st = cells(grid, A)
    gl = set(cells(grid, B))
    if not st or not gl:
        print("  %2d %-7s %s->%s: no legal cell (start %d, goal %d)"
              % (n, net, desc(A), desc(B), len(st), len(gl)), flush=True)
        total_no += 1
        continue
    path, cross, exp, closest = probe.astar(grid, st[:24], gl, 25.0, conflict=False)
    if path is None:
        print("  %2d %-7s %s->%s: NO PATH (closest %.2fmm, %d expanded)"
              % (n, net, desc(A), desc(B), closest[0] * M.step, exp), flush=True)
        total_no += 1
        continue
    ln = sum(((path[q][1] - path[q - 1][1]) ** 2
              + (path[q][2] - path[q - 1][2]) ** 2) ** 0.5
             for q in range(1, len(path))) * M.step
    p0 = grid.xy(path[0][1], path[0][2])
    p1 = grid.xy(path[-1][1], path[-1][2])
    a0 = M.attach_pt(p0[0], p0[1], [A])
    a1 = M.attach_pt(p1[0], p1[1], [B])
    pre = (a0[0], a0[1], path[0][0]) if a0 else None
    post = (a1[0], a1[1], path[-1][0]) if a1 else None
    nt, nv, nr = M.emit(net, grid, path, pre=pre, post=post)
    print("  %2d %-7s %s->%s: %6.2fmm  %2d trk %d via  %s%s"
          % (n, net, desc(A), desc(B), ln, nt, nv,
             "" if a0 else "NO-ATTACH-A ",
             "" if a1 else "NO-ATTACH-B"), flush=True)
    total_ok += 1
    total_len += ln
    worst = max(worst, (ln, "%s %d" % (net, n)))

print("\nbridged %d pair(s), %d unreachable, %.1fmm of new copper, %.1fs"
      % (total_ok, total_no, total_len, time.time() - t0), flush=True)
if worst[1]:
    print("longest: %.1fmm (%s)" % worst, flush=True)
if DRRY:
    print("--dry: nothing written", flush=True)
else:
    board.Save(OUT)
    print("saved %s" % OUT, flush=True)
