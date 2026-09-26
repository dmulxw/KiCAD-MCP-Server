"""route40 with rip-up-and-reroute, because plain greedy provably loses here.

route40 laid 15/35 pins on the widened two-header base.  The failures were not
long-haul capacity.  _pair.py on ROW11 and ROW2 -- two of the thirteen that
stopped at `closest ~1.00mm` -- says the same thing both times:

    start = the header pad        (legal pocket: 432 cells)
    goal  = the net's OWN copper  (island: 86558 cells)
    the two are DIFFERENT components, and they are 7mm apart

A 432-cell pocket is a pad boxed in on three sides.  A net whose trunk is 7mm
away failed because a *neighbouring pin's* freshly-laid route ran through the
gap while it was open.  J1B pin 2 (ROW11) failed, then pin 1 (ROW10) routed
67.8mm through the same corridor.  Whichever pin goes first wins.

That is not a capacity wall, it is an ordering artefact, and the standard
answer is to undo the specific copper that is in the way and let both nets try
again with knowledge of each other.  So:

  * every segment this run lays is recorded against the task that laid it
  * a failed search reports `closest`, the nearest it got to its goal
  * the other-net copper around that point is the blocker
  * the task that laid the blocker is ripped back to unrouted and re-queued
  * the failed task goes to the FRONT of the queue -- it needs the corridor
    now, and the re-queued task will route around it

Ripping is per-task rather than per-segment on purpose: a net's copper is a
chain, so removing one link in the middle can leave the rest of the chain
attached to nothing while still looking routed.  Undoing the whole task is
coarse but it always leaves the net honestly unrouted.

    SRC=.. OUT=.. python route40r.py [--maxrip N] [--dump]
"""
import collections
import os
import sys
import time

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402
import emitlib as M                                                  # noqa: E402
import probe                                                         # noqa: E402

S = 1e6
SRC = os.environ.get("SRC", "_fh0.kicad_pcb")
OUT = os.environ.get("OUT", "_fh0_rr.kicad_pcb")
MAXRIP = int(os.environ.get("MAXRIP", "6"))
RADIUS = float(os.environ.get("RADIUS", "0.6"))

# Same order as route40: ROW3/ROW5 first per the standing instruction, then
# J1B bottom-up, then J1A bottom-up.  Order still matters -- it decides who
# gets ripped first -- but it is no longer decisive, which is the point.
TASKS = [
    ("ROW3", "J1A", 1), ("ROW5", "J1A", 20),
    ("+3V3", "J1B", 20), ("GND", "J1B", 16),
    ("CSEL9", "J1B", 15), ("CSEL8", "J1B", 14), ("CSEL7", "J1B", 13),
    ("CSEL6", "J1B", 12), ("CSEL5", "J1B", 11),
    ("CSEL2", "J1B", 10), ("CSEL1", "J1B", 9), ("CSEL0", "J1B", 8),
    ("ROW20", "J1B", 7), ("ROW19", "J1B", 6), ("ROW18", "J1B", 5),
    ("ROW15", "J1B", 4), ("ROW12", "J1B", 3), ("ROW11", "J1B", 2),
    ("ROW10", "J1B", 1),
    ("GND", "J1A", 19), ("GND", "J1A", 16),
    ("CSEL3", "J1A", 15), ("CSEL4", "J1A", 14),
    ("ROW17", "J1A", 13), ("ROW16", "J1A", 12), ("ROW14", "J1A", 11),
    ("ROW13", "J1A", 10), ("ROW9", "J1A", 9), ("ROW8", "J1A", 8),
    ("ROW7", "J1A", 7), ("ROW6", "J1A", 6), ("ROW4", "J1A", 5),
    ("ROW2", "J1A", 4), ("ROW1", "J1A", 3), ("ROW0", "J1A", 2),
]

board = pcbnew.LoadBoard(SRC)
M.bind(board, st=0.1)
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
print("board %s: %d track(s)  step %.2f keep %.3f pad_keep %.3f  maxrip %d r %.2fmm"
      % (SRC, len(list(board.GetTracks())), M.step, M.keep, M.pad_keep,
         MAXRIP, RADIUS), flush=True)

GRAVE = []                  # board.Remove() hands the item to Python; if the
                            # proxy is GC'd SWIG loses its process-wide type
                            # table and every later LoadBoard returns a bare
                            # SwigPyObject.  Keep them all alive to the end.


def uid(it):
    return it.m_Uuid.AsString().replace("-", "").lower()


def snap():
    return {uid(t): t for t in board.GetTracks()}


def bbox(it):
    bb = it.GetBoundingBox()
    return (bb.GetLeft() / S, bb.GetTop() / S, bb.GetRight() / S, bb.GetBottom() / S)


def dist_to_box(px, py, b):
    dx = max(b[0] - px, px - b[2], 0.0)
    dy = max(b[1] - py, py - b[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


laid = {}                   # task -> {"net":.., "items":[..]}
queue = list(TASKS)
rips = collections.Counter()
results = {}
t_all = time.time()
rounds = 0

while queue:
    task = queue.pop(0)
    netname, ref, pin = task
    rounds += 1
    if rounds > 400:
        print("*** round cap hit; giving up on the rest", flush=True)
        for t in [task] + queue:
            results[t] = "cap"
        break

    t0 = time.time()
    tag = "%s %s.%-2d" % (netname, ref, pin)
    obstacles = [it for it in M.fresh() if it.GetNetname() != netname]
    g = M.make_grid(obstacles)
    mine = M.netcopper(netname)
    goals = M.goals_of(g, mine)
    src = fps[ref].FindPadByNumber(str(pin))
    c = src.GetPosition()
    if not goals:
        print("   %-13s no goal cell  <-- net owns no copper" % tag, flush=True)
        results[task] = "nog"
        continue

    before = snap()
    ci, cj = g.ij(c.x / S, c.y / S)
    st = M.starts_near(g, src, r=20) or [(M.LAYERS[0], ci, cj)]
    path, cross, exp, closest = probe.astar(g, st, goals, 25.0, conflict=False)

    if path is None:
        where = "?" if closest[1] is None else "%d,%.2f,%.2f" % (
            closest[1][0], g.x0 + closest[1][1] * M.step,
            g.y0 + closest[1][2] * M.step)
        # Who is standing on the spot the search could not get past?
        blockers = []
        if closest[1] is not None:
            px = g.x0 + closest[1][1] * M.step
            py = g.y0 + closest[1][2] * M.step
            for otask, rec in laid.items():
                if otask == task or otask not in results or results[otask] != "ok":
                    continue
                if any(dist_to_box(px, py, bbox(it)) <= RADIUS for it in rec["items"]):
                    blockers.append(otask)
        if not blockers or rips[task] >= MAXRIP:
            print("   %-13s NO PATH  expanded %d  closest %.2fmm  @%s  %4.0fs%s"
                  % (tag, exp, closest[0] * M.step, where, time.time() - t0,
                     "   (no rip: %s)" % ("budget spent" if rips[task] >= MAXRIP
                                          else "nothing rippable")), flush=True)
            results[task] = "none"
            continue

        rips[task] += 1
        for otask in blockers:
            rec = laid.pop(otask)
            for it in rec["items"]:
                board.Remove(it)
                GRAVE.append(it)
            results.pop(otask, None)
            if otask not in queue:
                queue.append(otask)
        print("   %-13s NO PATH  closest %.2fmm @%s  -> ripped %s  %4.0fs"
              % (tag, closest[0] * M.step, where,
                 ", ".join("%s %s.%s" % o for o in blockers), time.time() - t0),
              flush=True)
        queue.insert(0, task)          # retry with the corridor now clear
        continue

    ln = sum(((path[k][1] - path[k - 1][1]) ** 2
              + (path[k][2] - path[k - 1][2]) ** 2) ** 0.5
             for k in range(1, len(path))) * M.step
    pre = (c.x / S, c.y / S, path[0][0])
    p = g.xy(path[-1][1], path[-1][2])
    post = M.attach_pt(p[0], p[1], mine)
    post = None if post is None else (post[0], post[1], path[-1][0])
    nt, nv, nr = M.emit(netname, g, path, pre=pre, post=post)

    after = snap()
    new = [after[u] for u in after if u not in before]
    laid[task] = {"net": netname, "items": new, "mm": ln}
    results[task] = "ok"
    print("   %-13s %6.1fmm  %3d trk %2d via  %4.0fs"
          % (tag, ln, nt, nv, time.time() - t0), flush=True)

pcbnew.SaveBoard(OUT, board)
ok = [t for t in TASKS if results.get(t) == "ok"]
bad = [t for t in TASKS if results.get(t) != "ok"]
print("\n%d/%d pin(s) routed   (rip-ups: %d across %d task(s))"
      % (len(ok), len(TASKS), sum(rips.values()), len(rips)), flush=True)
if bad:
    print("failed: %s" % ", ".join("%s/%s" % (r, results.get(t, "?"))
                                   for t in bad for r in ["%s %s.%s" % t]), flush=True)
print("saved to %s   total %.1f min" % (OUT, (time.time() - t_all) / 60.0), flush=True)
