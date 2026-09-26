"""Go / no-go: after the class-aware rip, how far is every net from a header?

bothsides.py asked this on _final.kicad_pcb, i.e. with all 40 old fan-outs still
on the board as obstacles, and 12 nets were unreachable from both sides.  The
comb that sealed them was the fan-out itself.  _rip2.kicad_pcb has that comb
gone, so the same question now has a different answer, and it is the answer that
decides whether the interface change is buildable at all.

One grid per net instead of two: both headers' own pads are dropped from the
obstacle list at once, then A* is run twice over the same grid.  The headers are
80mm apart on opposite edges, so letting a J1A route see J1B's pads as free
costs nothing -- no J1A route comes near x=175.
"""
import sys, os, time
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W = 0.2
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

board = pcbnew.LoadBoard('_rip2.kicad_pcb')
GRAVE = []
j1a = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1A'][0]
j1b = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1B'][0]
print("J1A @%s  J1B @%s"
      % (j1a.GetPosition(), j1b.GetPosition()), flush=True)

hdr_pads = ({p.m_Uuid.AsString() for p in j1a.Pads()}
            | {p.m_Uuid.AsString() for p in j1b.Pads()})

edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

allc = list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                  for p in fp.Pads()]
print("board: %d copper item(s)" % len(allc), flush=True)

nets = sorted({it.GetNetname() for it in board.GetTracks() if it.GetNetname()}
              | {p.GetNetname() for fp in board.GetFootprints()
                 for p in fp.Pads() if p.GetNetname()})
print("%d net(s): %s\n" % (len(nets), " ".join(nets)), flush=True)

t_all = time.time()
print("%-9s %8s %8s %9s   %s" % ("net", "J1A", "J1B", "grid s", "verdict"),
      flush=True)
res = {}
for n_on, name in enumerate(nets):
    t0 = time.time()
    items = [it for it in allc
             if it.GetNetname() != name
             and it.m_Uuid.AsString() not in hdr_pads]
    g = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
    g.build(items)
    t_build = time.time() - t0

    mine = [it for it in allc if it.GetNetname() == name
            and it.m_Uuid.AsString() not in hdr_pads]
    goals = {gc for gc in replan.cells_of(g, mine, LAYERS)
             if g.OK[gc[0]][gc[2], gc[1]]}

    out = {}
    for tag, fp in (("J1A", j1a), ("J1B", j1b)):
        if not goals:
            out[tag] = ("nog", None)
            continue
        st = list(dict.fromkeys(replan.cells_of(g, list(fp.Pads()), LAYERS)))
        path, cross, exp, closest = probe.astar(g, st, goals, 25.0, conflict=False)
        if path is None:
            out[tag] = ("none", closest[0] * step)
        else:
            out[tag] = ("ok", sum(
                ((path[k][1]-path[k-1][1])**2
                 + (path[k][2]-path[k-1][2])**2)**0.5
                for k in range(1, len(path))) * step)
    res[name] = out

    def show(t):
        k, v = out[t]
        if k == "ok":
            return "%.1f" % v
        if k == "nog":
            return "no goal"
        return "x%.1f" % v            # unreachable, this close
    both = [v for k, v in out.values() if k == "ok"]
    verdict = ("LOCAL" if both and min(both) <= 60 else
               "LAP" if both else "unreachable")
    print("%-9s %8s %8s %9.1f   %s  [%d/%d]"
          % (name, show("J1A"), show("J1B"), t_build, verdict, n_on + 1, len(nets)),
          flush=True)

ok = [n for n in nets if any(k == "ok" for k, _ in res[n].values())]
loc = [n for n in ok if min(v for k, v in res[n].values() if k == "ok") <= 60]
bad = [n for n in nets if n not in ok]
print("\n%d net(s) reachable, of which %d local (<=60mm); %d unreachable"
      % (len(ok), len(loc), len(bad)), flush=True)
print("unreachable: %s" % (" ".join(bad) or "-"), flush=True)
print("total %.1f min" % ((time.time() - t_all) / 60.0), flush=True)
