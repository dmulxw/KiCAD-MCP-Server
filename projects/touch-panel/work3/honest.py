"""Decisive test: route all 40 pins with standard router semantics and DRC it.

Model M -- the one a real router uses, and the only one under which "reachable"
means "connectable":
  * every track and every pad is an obstacle -- including the other 39 header
    pins, which the earlier runs wrongly dissolved;
  * EXCEPT the source pin's own pad (you start on your own metal) and every
    piece of the target net's copper (you may touch your own net);
  * a goal cell is therefore a cell ON the target's copper, and the path's last
    cell is already in contact. Same at the start. No halo-grazing, no
    "closest 0.08mm away" pseudo-success.
"""
import sys, os, time
sys.path.insert(0, os.getcwd())
import numpy as np, pcbnew
import edgeflood as E, replan, probe

S = 1e6
layers = [pcbnew.F_Cu, pcbnew.B_Cu]

board = pcbnew.LoadBoard('../touch-panel.kicad_pcb')
edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
E.widen(board)
hdr = {}
for r_, x, y in (("J1A", E.LEFT_X, E.LEFT_Y), ("J1B", E.RIGHT_X, E.RIGHT_Y)):
    hdr[r_] = E.place(board, r_, E.HDR_LIB, E.HDR_FP, x, y, E.ASSIGN[r_])

plan = []
for r_ in ("J1A", "J1B"):
    for pin in sorted(E.ASSIGN[r_]):
        plan.append((r_, pin, E.ASSIGN[r_][pin]))
print("plan: %d pins" % len(plan))

order = [p for p in plan if p[2] in ("ROW3", "ROW5")]
order += [p for p in plan if p[2] not in ("ROW3", "ROW5")]
print("order: %s" % ", ".join("%s.%s=%s" % p for p in order[:6]))

nets = {}
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname():
            nets.setdefault(p.GetNetname(), []).append(p)

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

    # grid: everything except THIS pin's pad
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
    own_net = {}
    nm = np.array(nameof, dtype=object)
    for lay in layers:
        o = grid.OWN[lay]
        own_net[lay] = np.where(o >= 0, nm[np.where(o >= 0, o, 0)], "")

    # model M: the target net's own copper is not an obstacle
    OK = {lay: grid.OK[lay] | ((own_net[lay] == name) & (grid.D[lay] < keep))
          for lay in layers}
    VOK = grid.VOK | (np.logical_or.reduce([own_net[l] == name for l in layers])
                      & np.logical_and.reduce([grid.D[l] < pad_keep for l in layers]))
    import types
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
    goals = replan.cells_of(grid, tgt, layers)
    goals = {gc for gc in goals if OK[gc[0]][gc[2], gc[1]]}
    if not goals:
        res.append((ref, pin, name, "no legal goal")); continue

    path, cross, exp, closest = probe.astar(g, start, goals, 25.0, conflict=False)
    if path is None:
        res.append((ref, pin, name, "NO PATH closest %.2f steps" % closest[0]))
        print("  %-4s.%-2d %-6s NO PATH   goals %d  exp %d" % (ref, pin, name, len(goals), exp))
        continue
    nt, nv = replan.emit(board, name, g, path, lock=False)
    ln = sum(((path[k][1] - path[k - 1][1]) ** 2
              + (path[k][2] - path[k - 1][2]) ** 2) ** 0.5
             for k in range(1, len(path))) * step
    res.append((ref, pin, name, "ok"))
    print("  %-4s.%-2d %-6s %7.1fmm  %3d track %2d via  goals %d  exp %d  [%.0fs]"
          % (ref, pin, name, ln, nt, nv, len(goals), exp, time.time() - t0))

pcbnew.SaveBoard('_honest.kicad_pcb', board)
ok = sum(1 for r in res if r[3] == "ok")
print("\n%d / %d pins routed in %.0fs" % (ok, len(res), time.time() - t0))
for r in res:
    if r[3] != "ok":
        print("   FAIL %-4s pin %-2s %-6s %s" % r)
