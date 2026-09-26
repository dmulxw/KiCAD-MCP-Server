"""Which net can actually use J1 pad 4 / pad 6?

Companion to ``scan.py``. The pocket scan proved every J1 signal pin is sealed:
the largest pocket reach is y=204.50 (ROW19's pad 20) while ROW3's nearest own
copper sits at y=129.25. Moving ROW3/ROW5 to another J1 pin is therefore a swap
between two sealed pockets and cannot help.

The useful direction is the reverse. Pads 4 and 6 have a small pocket of their
own, and some net's copper may already pass through it. Put *that* net on the
pin and the pin is connected by construction; ROW3/ROW5 then move to the new
header, whose pins sit in open space.

This measures exactly that, net by net: swap the pad's net, rebuild the grid
with the candidate net's own copper excluded from obstacles, and ask A* for a
path from the pad to that net's copper. PATH means the pin can carry that net.

Copper zones are reported separately -- ``obstacles()`` walks tracks and pads
only, so a filled GND pour is invisible to the search. If one overlaps the
pocket, the connection is a via into the pour and no search is needed.

    python cando.py <board> [--pads 4 6] [--box X0 Y0 X1 Y1]
"""

import argparse
import sys
import time

import pcbnew

from probe import NGrid, astar, TRACK_W, VIA_DIA
from replan import cells_of, pad_cells

S = 1e6

#: A J1 signal pad is 0.3 x 1.3mm and its pocket is a couple of mm wide, so the
#: box only has to be big enough to catch the copper that passes beside it.
BOX = (125.40, 240.90, 129.40, 249.00)


def items_of(board, exclude):
    """Every piece of routed copper and every pad not on `exclude`."""
    out = [t for t in board.GetTracks() if t.GetNetname() != exclude]
    for fp in board.GetFootprints():
        out += [p for p in fp.Pads() if p.GetNetname() != exclude]
    return out


def reachable(board, pad, num, target, step, safety, edge_clear):
    """PATH/NO PATH from `pad` (already set to `target`) to `target`'s copper.

    The pad under test has to be dropped from its own goal set by *reference and
    number*, never by identity: SWIG builds a fresh proxy on every
    ``fp.Pads()`` iteration, so ``p is not pad`` is always true and the pad
    ends up adjacent to itself -- a 2-cell "PATH" that means nothing.
    """
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    keep = 0.2 + TRACK_W / 2 + safety
    pad_keep = 0.2 + VIA_DIA / 2 + safety
    grid = NGrid(board, step, keep, edge_clear + TRACK_W / 2 + safety,
                 pad_keep, edge_clear + VIA_DIA / 2 + safety, layers)
    grid.build(items_of(board, target))

    start = pad_cells(grid, pad, layers)
    if not start:
        return None, "pad has no legal cell of its own", None

    own = [t for t in board.GetTracks() if t.GetNetname() == target]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != target:
                continue
            if fp.GetReference() == "J1" and p.GetNumber() == num:
                continue
            own.append(p)
    goals = cells_of(grid, own, layers) - set(start)
    if not goals:
        return None, "no other copper on this net", None

    path, cross, exp, closest = astar(grid, start, goals, 25.0, conflict=False)
    return path, None, closest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--pads", nargs="+", default=["4", "6"])
    ap.add_argument("--box", nargs=4, type=float, default=list(BOX),
                    metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--safety", type=float, default=0.04)
    a = ap.parse_args()
    bx0, by0, bx1, by1 = a.box

    board = pcbnew.LoadBoard(a.src)
    edge_clear = board.GetDesignSettings().m_CopperEdgeClearance / S
    j1 = next(fp for fp in board.GetFootprints() if fp.GetReference() == "J1")

    print("=== zones ===")
    zones = list(board.Zones())
    if not zones:
        print("  none -- the board is tracks and pads only, so the search "
              "model is complete")
    for z in zones:
        bb = z.GetBoundingBox()
        print(f"  net {z.GetNetname()!r} filled={bool(z.IsFilled())} "
              f"bbox x {bb.GetLeft()/S:.2f}..{bb.GetRight()/S:.2f} "
              f"y {bb.GetTop()/S:.2f}..{bb.GetBottom()/S:.2f}")

    print(f"\n=== pads ===")
    for num in a.pads:
        p = j1.FindPadByNumber(num)
        pos = p.GetPosition()
        print(f"  J1.{num}: net {p.GetNetname()!r} at "
              f"({pos.x/S:.3f},{pos.y/S:.3f})")

    # Which nets have copper in the pocket box at all? Only those can be
    # reached; testing all 40 would be minutes of search for nothing.
    cand = set()
    def consider(it):
        sh = it.GetBoundingBox()
        if (sh.GetRight() / S < bx0 or sh.GetLeft() / S > bx1
                or sh.GetBottom() / S < by0 or sh.GetTop() / S > by1):
            return
        n = it.GetNetname()
        if n and n not in ("ROW3", "ROW5"):
            cand.add(n)
    for t in board.GetTracks():
        consider(t)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            consider(p)

    print(f"\n=== candidates with copper in "
          f"x[{bx0},{bx1}] y[{by0},{by1}] ===")
    print("  " + ", ".join(sorted(cand)))

    print()
    for num in a.pads:
        for target in sorted(cand):
            t = time.time()
            b = pcbnew.LoadBoard(a.src)
            pad = next(fp for fp in b.GetFootprints()
                       if fp.GetReference() == "J1").FindPadByNumber(num)
            ni = b.FindNet(target)
            if ni is None:
                print(f"  J1.{num} -> {target:<8} net not found")
                continue
            pad.SetNet(ni)
            path, err, closest = reachable(b, pad, num, target, a.step,
                                           a.safety, edge_clear)
            if err:
                print(f"  J1.{num} -> {target:<8} {err}")
            elif path:
                ln = 0.0
                for k in range(1, len(path)):
                    (l0, i0, j0), (l1, i1, j1) = path[k - 1], path[k]
                    if l0 == l1:
                        ln += ((i1 - i0) ** 2 + (j1 - j0) ** 2) ** 0.5 * a.step
                print(f"  J1.{num} -> {target:<8} PATH   {ln:6.2f}mm  "
                      f"{len(path)} cells  [{time.time()-t:.0f}s]")
            else:
                d, at = closest if closest[1] else (0, None)
                where = (f"({at[1]*a.step+0:.2f},{at[2]*a.step+0:.2f})"
                         if at else "-")
                print(f"  J1.{num} -> {target:<8} NO PATH  closest "
                      f"{d*a.step:.2f}mm  [{time.time()-t:.0f}s]")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
