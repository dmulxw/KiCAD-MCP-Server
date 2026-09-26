"""Can ROW3 leave J1 pad 4 at all -- even with no safety margin?

The whole re-plan rests on this number, so it deserves a control. The router
normally keeps a 0.04mm cushion on top of the 0.2mm design rule; that cushion
is what makes an already-routed net score NO PATH against its own copper, since
its existing trace sits exactly on the rule and a fresh 0.34mm-wide test does
not fit beside it. So a bare "NO PATH" proves nothing on its own.

Three questions, all on the untouched board:

* pad 20 -> ROW19, which IS routed: must come back PATH. If it does not, the
  test is broken and nothing else it says can be believed.
* pad 1  -> ROW0, which IS routed but packed tight: may legitimately say NO
  PATH. That is the known artifact, and it calibrates the pessimistic end.
* pad 4  -> ROW3 and pad 6 -> ROW5, which are NOT routed: these are the test.
  ROW3 has no trace of its own anywhere, so there is no artifact to blame.

Run at safety 0.04 (the router's own margin) and at 0.00 (the bare design
rule), so the answer can be stated as "cannot, even with zero margin".

    python zero.py <board>
"""

import argparse

import pcbnew

from probe import NGrid, astar, TRACK_W, VIA_DIA
from replan import cells_of, pad_cells

S = 1e6

CASES = [
    ("20", "ROW19", "control: routed"),
    ("1", "ROW0", "control: routed, packed"),
    ("4", "ROW3", "TEST"),
    ("6", "ROW5", "TEST"),
]


def test(src, padnum, net, safety, step, edge_clear):
    board = pcbnew.LoadBoard(src)
    j1 = next(fp for fp in board.GetFootprints() if fp.GetReference() == "J1")
    pad = j1.FindPadByNumber(padnum)
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]

    keep = 0.2 + TRACK_W / 2 + safety
    grid = NGrid(board, step, keep, edge_clear + TRACK_W / 2 + safety,
                 0.2 + VIA_DIA / 2 + safety,
                 edge_clear + VIA_DIA / 2 + safety, layers)

    items = [t for t in board.GetTracks() if t.GetNetname() != net]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                items.append(p)
    grid.build(items)

    start = pad_cells(grid, pad, layers)
    if not start:
        return None, None, 0, 0, "pad has no cells"

    own = [t for t in board.GetTracks() if t.GetNetname() == net]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            if fp.GetReference() == "J1" and p.GetNumber() == padnum:
                continue
            own.append(p)
    goals = cells_of(grid, own, layers) - set(start)
    if not goals:
        return None, None, len(start), 0, "no own copper"

    path, cross, exp, closest = astar(grid, start, goals, 25.0, conflict=False)
    return path, closest, len(start), len(goals), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=float, default=0.05)
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.src)
    edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
    n_track = {}
    for t in board.GetTracks():
        n = t.GetNetname()
        n_track[n] = n_track.get(n, 0) + 1
    print("how much copper each net already has:")
    for num, net, tag in CASES:
        print(f"  {net:<6} {n_track.get(net, 0):5d} track(s)   ({tag})")

    for safety in (0.04, 0.00):
        print(f"\n=== safety margin {safety:.2f}mm "
              f"(keep = {0.2 + 0.1 + safety:.2f}mm) ===")
        for num, net, tag in CASES:
            path, closest, ns, ng, err = test(a.src, num, net, safety, a.step,
                                              edge_clear)
            if err:
                print(f"  J1.{num} -> {net:<6} {err}")
                continue
            if path:
                ln = sum(((path[k][1] - path[k-1][1]) ** 2
                          + (path[k][2] - path[k-1][2]) ** 2) ** 0.5
                         for k in range(1, len(path))) * a.step
                print(f"  J1.{num} -> {net:<6} PATH     {ln:7.2f}mm  "
                      f"({tag})")
            else:
                d = closest[0] * a.step if closest[1] else float("inf")
                print(f"  J1.{num} -> {net:<6} NO PATH  closest "
                      f"{d:7.2f}mm  ({tag})")


if __name__ == "__main__":
    main()
