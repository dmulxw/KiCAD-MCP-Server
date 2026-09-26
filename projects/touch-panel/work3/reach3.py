"""Did clearing the strip actually free the eleven?

reach2.py, on _rip2 (strip intact): 242/253 reachable, and the 11 that are not
are exactly the strip-only pockets.  rip3.py then took 361 other-net segments
out of the strip and left those pockets alone.  Same question, new board.

Focused net list -- a full 253-net sweep is 17 minutes and only these changed.
Pass names on the command line, or nothing for the default problem set.
"""
import sys, os, time
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W = 0.2
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

DEF = (["+3V3"] + ["CSEL%d" % k for k in (0, 1, 2, 6, 7, 8, 9)]
       + ["PAD20%d" % k for k in range(1, 11)]
       + ["ROW20", "ROW0", "COL0", "COL9", "GND", "CSEL3"])
NAMES = sys.argv[1:] or DEF
BOARD = os.environ.get("BOARD", "_rip3.kicad_pcb")

board = pcbnew.LoadBoard(BOARD)
GRAVE = []
j1a = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1A'][0]
j1b = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1B'][0]
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
print("board %s: %d copper item(s)\n" % (BOARD, len(allc)), flush=True)
print("%-9s %8s %8s %6s   %s" % ("net", "J1A", "J1B", "grid s", "verdict"),
      flush=True)

t_all = time.time()
res = {}
for name in NAMES:
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
        path, cross, exp, closest = probe.astar(g, st, goals, 25.0,
                                                conflict=False)
        out[tag] = (("none", closest[0] * step) if path is None else
                    ("ok", sum(((path[k][1]-path[k-1][1])**2
                                + (path[k][2]-path[k-1][2])**2)**0.5
                               for k in range(1, len(path))) * step))
    res[name] = out

    def show(t):
        k, v = out[t]
        return "no goal" if k == "nog" else ("%.1f" % v if k == "ok"
                                             else "x%.1f" % v)
    both = [v for k, v in out.values() if k == "ok"]
    verdict = ("LOCAL" if both and min(both) <= 60 else
               "LAP" if both else "unreachable")
    print("%-9s %8s %8s %6.1f   %s" % (name, show("J1A"), show("J1B"),
                                       t_build, verdict), flush=True)

ok = [n for n in NAMES if any(k == "ok" for k, _ in res[n].values())]
print("\n%d/%d reachable; still unreachable: %s"
      % (len(ok), len(NAMES),
         " ".join(n for n in NAMES if n not in ok) or "-"), flush=True)
print("total %.1f min" % ((time.time() - t_all) / 60.0), flush=True)
