"""Delete the old fan-out of the nets whose header pads moved, so they can be
laid again from the far end.

Incremental routing assumes a *pad* moved: the net's copper is still a valid path
and the new pad only has to reach it.  Here 44 pads moved -- J1 and J2 slid 10.8 mm
south as whole footprints -- so every trace that used to leave those pads now ends
in empty space, and the trunks that fan out west of the old column (x 8.0..10.6,
five parallel runs) sit exactly where the new pads need to breathe.  The router
then tries to squeeze a new pad into a corridor that is already full of the net's
own dead copper, and the repair loop cannot help: rip() only touches copper the
router laid this run, never the board's own (see blocking_nets/route_all).

The honest operation is the one a person would do -- the part moved, so re-lay
what touched it.  Delete those nets' tracks and vias; everything else on the board
stays, and route.py's INCREMENTAL pass then sees it as frozen context *and*
obstacle, which is exactly right.  GND is not in the list: it is carried by the
pour and by zones, and has no tracks of its own to remove.

  python _clear_moved.py <in.kicad_pcb> <out.kicad_pcb>
"""
import sys

import pcbnew

MOVED = [
    "+3V3", "+5V",
    "BTN_ACT", "BTN_RST", "BTN_VOL_DN", "BTN_VOL_UP",
    "I2C_SCL", "I2C_SDA",
    "I2S_BCK", "I2S_DI", "I2S_DO", "I2S_MCK", "I2S_WS",
    "IO9", "IO10", "IO11", "IO12", "IO13", "IO14", "IO17", "IO18",
    "IO38", "IO39", "IO42", "IO43", "IO44", "IO48",
    "LCD_CS", "LCD_DC", "LCD_RST", "LCD_SCK", "LCD_SDA",
]


def main(src, dst):
    board = pcbnew.LoadBoard(src)
    if board is None:
        sys.exit("LoadBoard returned None for " + src)
    want = set(MOVED)

    # Read everything into plain values BEFORE removing anything: board.Remove()
    # invalidates other outstanding proxies (see the notes in place.py).
    doomed = []
    per_net = {}
    for t in board.GetTracks():
        net = str(t.GetNetname())
        if net not in want:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            per_net[net] = per_net.get(net, 0) + 1
        else:
            per_net[net] = per_net.get(net, 0) + 1
        doomed.append(t)

    frozen = doomed                      # keep the proxies alive until Save()
    for t in doomed:
        board.Remove(t)

    print("removed %d track(s)/via(s) belonging to %d moved net(s):"
          % (len(doomed), len(per_net)))
    for n in MOVED:
        print("  %-10s %3d" % (n, per_net.get(n, 0)))
    missing = [n for n in MOVED if n not in per_net]
    if missing:
        print("  NOTE: no copper at all for: %s" % " ".join(missing))

    board.Save(dst)
    print("\nsaved", dst, "  (keep-alive held %d)" % len(frozen))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
