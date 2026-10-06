"""Delete the tracks and vias of named nets, so route.py's incremental pass can
lay them again.

_clear_moved.py does this for the whole set of nets whose header pads moved.  This
is the same operation narrowed to a handful, which is what a single sealed pour
pocket around J4.7 needs: the seal is IO14's B.Cu jog under the pad, and moving
one trace is a far smaller change than re-laying 32 nets.  route.py deletes
nothing (see the INCREMENTAL note), so the copper has to go before it runs, or it
would simply be absorbed as frozen context and left exactly where it is.

  python _clear_nets.py <in.kicad_pcb> <out.kicad_pcb> NET[,NET...]
"""
import sys

import pcbnew


def main(src, dst, names):
    board = pcbnew.LoadBoard(src)
    if board is None:
        sys.exit("LoadBoard returned None for " + src)
    want = set(names)

    # Read everything into plain values BEFORE removing anything: board.Remove()
    # invalidates other outstanding proxies.
    doomed = []
    per_net = {}
    for t in board.GetTracks():
        net = str(t.GetNetname())
        if net not in want:
            continue
        per_net[net] = per_net.get(net, 0) + 1
        doomed.append(t)

    frozen = doomed                      # keep the proxies alive until Save()
    for t in doomed:
        board.Remove(t)
    del frozen

    print("removed %d track(s)/via(s) belonging to %d net(s):"
          % (len(doomed), len(per_net)))
    for n in names:
        print("  %-10s %3d" % (n, per_net.get(n, 0)))
    missing = [n for n in names if n not in per_net]
    if missing:
        print("  NOTE: no copper at all for: %s" % " ".join(missing))

    board.Save(dst)
    print("\nsaved", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3].split(","))
