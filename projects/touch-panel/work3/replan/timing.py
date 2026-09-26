"""How long does one NGrid build + one A* take at a given step?

The replan runs a search per priority net and per re-routed net, so if a
single search is minutes long the whole plan is impractical at that step --
worth knowing before committing to the run rather than after.
"""
import sys
import time

import pcbnew

sys.path.insert(0, "..")
from probe import NGrid, astar  # noqa: E402
from replan import cells_of, pad_cells  # noqa: E402

S = 1e6
for step in (float(x) for x in sys.argv[1:] or ["0.05"]):
    board = pcbnew.LoadBoard("p1.kicad_pcb")
    j1 = next(fp for fp in board.GetFootprints() if fp.GetReference() == "J1")
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    keep = 0.2 + 0.1 + 0.04
    t = time.time()
    grid = NGrid(board, step, keep, keep, keep, keep, layers)
    n = 0
    for it in board.GetTracks():
        it.GetNetname()
        n += 1
    others = [x for x in board.GetTracks() if x.GetNetname() != "ROW3"]
    grid.build(others)
    tb = time.time() - t
    print(f"step {step}: grid {grid.nx}x{grid.ny} = "
          f"{grid.nx * grid.ny / 1e6:.2f}M cells/layer, "
          f"{len(others)} item(s), build {tb:.1f}s")

    src = next(p for p in j1.Pads() if p.GetNetname() == "ROW3")
    own = [x for x in board.GetTracks() if x.GetNetname() == "ROW3"]
    for fp in board.GetFootprints():
        own += [p for p in fp.Pads() if p.GetNetname() == "ROW3"]
    start = pad_cells(grid, src, layers)
    goals = cells_of(grid, own, layers) - set(start)
    t = time.time()
    path, cross, exp, close = astar(grid, start, goals, 25.0, conflict=False)
    print(f"          start {len(start)} goal {len(goals)} -> "
          f"{'PATH ' + str(len(path)) + ' cells' if path else 'NO PATH'}"
          f", expanded {exp}, {time.time() - t:.1f}s")
    sys.stdout.flush()
