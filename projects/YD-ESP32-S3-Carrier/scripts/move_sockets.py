"""Slide the dev board south so its USB edge sits flush with the board edge, and
put the two panel headers in the band that opens up at the bottom right.

The 100x74 board grew south, but the sockets stayed where the 100x64 board put
them: J1/J2 still end at y 61.34, so the dev board's body stops at y 63.25 and
its Type-C shell now sits *inside* the outline, over y 63.25..74.  The plug has
to be flush with the bottom edge, so the sockets move down by exactly the 10.8 mm
the board grew (8.00 -> 18.80); the body then ends at 74.05, level with the edge.

That move drives the dev board's pin column through the old panel header band --
J8/J10 used to run from x 2.0 at y 68.1 / 71.8, straight across the new pin
column's path.  They move east to x 50.0, into the 48 mm of band that was empty
at the bottom right; the strip under J10 keeps 0.93 mm to the board edge and the
gap between the two rows stays 4.7 mm, same as before.

Both moves keep the *rotation* and only translate, so the pad numbering, the
netlist and the footprint library links are all untouched.  The Reference and
Value text fields are translated with their part -- they are drawn at absolute
coordinates and would otherwise be left behind at the old position.

Nothing but footprint geometry is written: tracks, vias and zones are left for
route.py and pour.py to deal with, since the pads have moved out from under them.

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" scripts/move_sockets.py [board]
"""
import sys

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

# reference -> absolute (x, y) of the footprint origin, in mm
MOVETO = {
    "J1":  (11.00, 18.80),   # was (11.00,  8.00)  +10.8 in y
    "J2":  (36.40, 18.80),   # was (36.40,  8.00)
    "J8":  (50.00, 67.10),   # was ( 2.00, 68.10)  +48.0 in x, -1.0 in y
    "J10": (50.00, 71.80),   # was ( 2.00, 71.80)  +48.0 in x
}


def main(out):
    board = pcbnew.LoadBoard(BOARD)
    if board is None:
        sys.exit("LoadBoard returned None for " + BOARD)

    # Footprint proxies are taken once and held: FindFootprintByReference in a
    # loop hands back fresh proxies for board-owned pointers, and collecting them
    # leaves the board's own list holding freed entries (see place.py).
    by_ref = {str(f.GetReference()): f for f in board.GetFootprints()}

    touched = {}
    for ref, (tx, ty) in sorted(MOVETO.items()):
        fp = by_ref.get(ref)
        if fp is None:
            sys.exit("%s is not on the board" % ref)
        old = fp.GetPosition()
        dx = pcbnew.FromMM(tx) - old.x
        dy = pcbnew.FromMM(ty) - old.y

        # Fields first, while the footprint is still where the text was drawn --
        # the delta is the same either way, but reading them here keeps the two
        # moves visibly independent.
        moved_fields = []
        for name in ("Reference", "Value"):
            if not fp.HasField(name):
                continue
            f = fp.GetField(name)
            p = f.GetPosition()
            f.SetPosition(pcbnew.VECTOR2I(p.x + dx, p.y + dy))
            moved_fields.append(name)

        fp.SetPosition(pcbnew.VECTOR2I(old.x + dx, old.y + dy))
        new = fp.GetPosition()
        nets = sorted({str(p.GetNetname()) for p in fp.Pads()
                       if str(p.GetNetname()) not in ("", "GND")})
        for n in nets:
            touched.setdefault(n, []).append(ref)
        print("  %-4s (%7.2f,%7.2f) -> (%7.2f,%7.2f)   rot %5.1f  %2d pads, "
              "%d signal net(s)  fields %s"
              % (ref, pcbnew.ToMM(old.x), pcbnew.ToMM(old.y),
                 pcbnew.ToMM(new.x), pcbnew.ToMM(new.y),
                 fp.GetOrientationDegrees(), fp.GetPadCount(), len(nets),
                 ",".join(moved_fields) or "none"))

    print("\n%d net(s) gained a moved pad (GND excluded -- the pour carries it):"
          % len(touched))
    print("  " + " ".join(sorted(touched)))

    board.Save(out)
    print("\nsaved", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else BOARD)
