"""Would two edge headers route?  Measured on the WALL-REMOVED board.

Every earlier 40-pin-from-headers run (_band, honest, ...) was made with the
GND wall still in place.  The wall is now gone, and it spanned y 118.91-146.92
-- the west end of ROW2/3/4/5/6's trunks -- so the reachability of those trunk
ends is a genuinely new question, not a re-run.

Isolated cost per net: min over all 20 pads of the header, one A* per header.
This is the optimistic bound; if the optimistic bound is already a lap of the
board, sequential routing cannot possibly converge.
"""
import sys, os, math
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E, replan, probe

S = 1e6
TRACK_W = 0.2
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

board = pcbnew.LoadBoard('_final.kicad_pcb')
GRAVE = []
# _final is already widened (outline at 89.95 / 181.05) and already has the wall
# out and GND bridged, so no E.widen() and no wall pass here.

j1b = E.place(board, "J1B", E.HDR_LIB, E.HDR_FP, E.RIGHT_X, E.RIGHT_Y, {})
print("J1B @(%.2f,%.2f)  %d pad(s), none netted"
      % (E.RIGHT_X, E.RIGHT_Y, len(list(j1b.Pads()))), flush=True)
j1a = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1A'][0]

edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + TRACK_W/2 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

def make_grid(items):
    g = E.NGrid(board, step, keep, egk, pad_keep, vek, LAYERS)
    g.build(items)
    return g

j1a_pads = {p.m_Uuid.AsString() for p in j1a.Pads()}
j1b_pads = {p.m_Uuid.AsString() for p in j1b.Pads()}
hdr_pads = j1a_pads | j1b_pads

def start_cells(grid, fp):
    """The header's own pads, as cells.

    A pad is 1.7mm across and pad_keep is 0.54mm, so the nearest *legal* cell is
    1.39mm out -- searching a +/-4-cell ball around the centre finds nothing at
    all and the search dies with an empty start set.  Instead the header's own
    pads are dropped from the obstacle list, exactly as matrix.py did: the wire
    begins on the pad, so it can never have to route around its own pin.  The
    start cells come straight off the pad copper and astar seeds them at g=0.
    """
    return list(dict.fromkeys(replan.cells_of(grid, list(fp.Pads()), LAYERS)))

ROWS = ["ROW%d" % k for k in range(21)]
NETS = ROWS + ["CSEL%d" % k for k in range(10)] + ["GND", "+3V3"]

print("\n%-7s %10s %10s   %s" % ("net", "J1A best", "J1B best", "verdict"), flush=True)
rows = []
for name in NETS:
    allc = list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                      for p in fp.Pads()]
    res = {}
    for tag, fp, own in (("A", j1a, j1a_pads), ("B", j1b, j1b_pads)):
        items = [it for it in allc
                 if it.GetNetname() != name
                 and it.m_Uuid.AsString() not in own]
        grid = make_grid(items)
        tgt = [it for it in allc if it.GetNetname() == name
               and it.m_Uuid.AsString() not in hdr_pads]
        goals = {gc for gc in replan.cells_of(grid, tgt, LAYERS)
                 if grid.OK[gc[0]][gc[2], gc[1]]}
        if not goals:
            res[tag] = ("nog", None)
            continue
        path, cross, exp, closest = probe.astar(grid, start_cells(grid, fp), goals,
                                                25.0, conflict=False)
        res[tag] = ("ok", None) if path is None else ("ok", sum(
            ((path[k][1]-path[k-1][1])**2 + (path[k][2]-path[k-1][2])**2)**0.5
            for k in range(1, len(path))) * step)
    fa = "%.1f" % res["A"][1] if res["A"][1] is not None else res["A"][0]
    fb = "%.1f" % res["B"][1] if res["B"][1] is not None else res["B"][0]
    best = min([v for _, v in res.values() if v is not None], default=None)
    verdict = ("LAP" if best is not None and best > 60 else
               "ok" if best is not None else "unreachable")
    print("%-7s %10s %10s   %s" % (name, fa, fb, verdict), flush=True)
    rows.append((name, res["A"][1], res["B"][1]))

print("\n=== summary ===", flush=True)
ok = [r for r in rows if min([v for v in (r[1], r[2]) if v is not None], default=1e9) <= 60]
lap = [r for r in rows if min([v for v in (r[1], r[2]) if v is not None], default=1e18) > 60]
dead = [r for r in rows if r[1] is None and r[2] is None]
print("  <=60mm from some header: %d" % len(ok))
print("  >60mm (a lap of the board): %d  %s" % (len(lap), [r[0] for r in lap]))
print("  unreachable from both: %d  %s" % (len(dead), [r[0] for r in dead]))
