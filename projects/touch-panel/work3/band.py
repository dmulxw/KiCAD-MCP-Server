"""Nearest-band pin reassignment, sequential honest routing, FPC deleted.

Same model M as honest.py -- every track and pad is an obstacle except the
source pin's own pad and the target net's own copper -- but with two changes
the measurements asked for:

* J1, the 40-pin 0.5mm FPC, is REMOVED. Its 40 netted pads in the bottom strip
  were both obstacles and goals in every earlier run.
* the pin allocation is regrouped by physical y band instead of by index, so
  each header only serves the ROWs whose copper actually sits beside it.

Ordering keeps standing task #4: ROW3 and ROW5 go first.
"""
import sys, os, time, types
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
GRAVE = []
layers = [pcbnew.F_Cu, pcbnew.B_Cu]

#: nearest-band split: each side serves the copper beside it.
#: ROW20 rides J1B pin 20 -- pin 11 is 29mm above ROW20's trunk and the
#: matrix shows the upper half of J1B cannot reach ROW20 at all (1.48M cells
#: expanded, no path), while pin 20 sits 6.6mm from that trunk.
BAND = {
    "J1A": {1: "ROW0", 2: "ROW1", 3: "ROW2", 4: "ROW3", 5: "ROW4",
            6: "ROW5", 7: "ROW6", 8: "ROW7", 9: "ROW8", 10: "ROW9",
            11: "CSEL0", 12: "CSEL1", 13: "CSEL2", 14: "CSEL3",
            15: "CSEL4", 16: "GND", 17: "GND", 18: "GND",
            19: "+3V3", 20: "+3V3"},
    "J1B": {1: "ROW10", 2: "ROW11", 3: "ROW12", 4: "ROW13", 5: "ROW14",
            6: "ROW15", 7: "ROW16", 8: "ROW17", 9: "ROW18", 10: "ROW19",
            11: "CSEL5", 12: "CSEL6", 13: "CSEL7", 14: "CSEL8",
            15: "CSEL9", 16: "GND", 17: "GND", 18: "+3V3",
            19: "+3V3", 20: "ROW20"},
}
for _r, _d in BAND.items():
    assert len(_d) == 20, _r
_all = [n for d in BAND.values() for n in d.values()]
_sig = [n for n in _all if n not in ("GND", "+3V3")]
print("assignment: %d pins, %d distinct nets" % (len(_all), len(set(_all))))
print("  signal nets unique : %s" % (len(_sig) == len(set(_sig))))
print("  GND x%d  +3V3 x%d" % (_all.count("GND"), _all.count("+3V3")))
assert len(_all) == 40
assert len(_sig) == len(set(_sig))
assert _all.count("GND") == 5 and _all.count("+3V3") == 4

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S

for fp in list(board.GetFootprints()):
    if fp.GetReference() == 'J1':
        board.Remove(fp); GRAVE.append(fp)
        print("removed J1 (FPC)")
E.widen(board)
hdr = {}
for r_, x, y in (("J1A", E.LEFT_X, E.LEFT_Y), ("J1B", E.RIGHT_X, E.RIGHT_Y)):
    hdr[r_] = E.place(board, r_, E.HDR_LIB, E.HDR_FP, x, y, BAND[r_])

plan = [(r_, pin, BAND[r_][pin]) for r_ in ("J1A", "J1B") for pin in sorted(BAND[r_])]
order = [p for p in plan if p[2] in ("ROW3", "ROW5")]
order += [p for p in plan if p[2] not in ("ROW3", "ROW5")]
print("first up: %s" % ", ".join("%s.%s=%s" % p for p in order[:4]))

step, safety, clearance = 0.1, 0.04, 0.2
keep = clearance + 0.1 + safety
pad_keep = clearance + 0.3 + safety
egk = edge_clear + clearance + safety
vek = egk + 0.3

res = []
t0 = time.time()
for ref, pin, name in order:
    src = [p for p in hdr[ref].Pads() if p.GetNetname() == name]
    if not src:
        res.append((ref, pin, name, "no pad")); continue
    src = src[0]

    items = list(board.GetTracks())
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.m_Uuid.AsString() != src.m_Uuid.AsString():
                items.append(p)
    grid = E.NGrid(board, step, keep, egk, pad_keep, vek, layers)
    grid.build(items)

    nameof = []
    for it in items:
        try: nameof.append(it.GetNetname())
        except Exception: nameof.append("")
    nm = np.array(nameof, dtype=object)
    own_net = {}
    for lay in layers:
        o = grid.OWN[lay]
        own_net[lay] = np.where(o >= 0, nm[np.where(o >= 0, o, 0)], "")

    OK = {lay: grid.OK[lay] | ((own_net[lay] == name) & (grid.D[lay] < keep))
          for lay in layers}
    VOK = grid.VOK | (np.logical_or.reduce([own_net[l] == name for l in layers])
                      & np.logical_and.reduce([grid.D[l] < pad_keep for l in layers]))
    g = types.SimpleNamespace()
    g.step, g.nx, g.ny, g.n = grid.step, grid.nx, grid.ny, grid.n
    g.layers, g.keep, g.D, g.OWN, g.VOK = layers, grid.keep, grid.D, grid.OWN, VOK
    g.OK, g.xy, g.ij, g.EG = OK, grid.xy, grid.ij, grid.EG

    c = src.GetPosition()
    ci, cj = grid.ij(c.x / S, c.y / S)
    start = [(lay, ci, cj) for lay in layers if OK[lay][cj, ci]]
    if not start:
        res.append((ref, pin, name, "start not free")); continue

    tgt = [it for it in items if getattr(it, "GetNetname", lambda: "")() == name]
    goals = {gc for gc in replan.cells_of(grid, tgt, layers)
             if OK[gc[0]][gc[2], gc[1]]}
    if not goals:
        res.append((ref, pin, name, "no legal goal")); continue

    path, cross, exp, closest = probe.astar(g, start, goals, 25.0, conflict=False)
    if path is None:
        res.append((ref, pin, name, "NO PATH closest %.2f steps" % closest[0]))
        print("  %-4s.%-2d %-6s NO PATH  goals %d  exp %d  [%.0fs]"
              % (ref, pin, name, len(goals), exp, time.time() - t0), flush=True)
        continue
    nt, nv = replan.emit(board, name, g, path, lock=False)
    ln = sum(((path[k][1] - path[k-1][1])**2 + (path[k][2] - path[k-1][2])**2)**0.5
             for k in range(1, len(path))) * step
    res.append((ref, pin, name, "ok"))
    print("  %-4s.%-2d %-6s %7.1fmm  %3d track %2d via  goals %d  exp %d  [%.0fs]"
          % (ref, pin, name, ln, nt, nv, len(goals), exp, time.time() - t0), flush=True)

pcbnew.SaveBoard('_band.kicad_pcb', board)
ok = sum(1 for r in res if r[3] == "ok")
print("\n%d / %d pins routed in %.0fs" % (ok, len(res), time.time() - t0))
for r in res:
    if r[3] != "ok":
        print("   FAIL %-4s pin %-2s %-6s %s" % r)
