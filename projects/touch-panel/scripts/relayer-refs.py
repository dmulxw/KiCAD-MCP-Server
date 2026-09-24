"""Move reference text that cannot be printed to the fabrication layer.

DRC reports 53 silkscreen warnings here, and they all come down to three
groups of reference designators that have nowhere legal to sit:

  TP1-TP10   The touch pads are a 5mm grid on 6.4mm pitch. The reference
             text is 1mm high and lands on the pad's own mask aperture
             ("clipped by solder mask"), and there is no room outside the
             pad before the next column's text begins.
  R22-R31    Ten 0402s on 2mm pitch along the bottom edge. "R22" is wider
             than the 2mm the layout gave each part.
  MH1-MH4    The mounting holes' reference text sits where the corner
             MOSFETs draw their bodies.

Anywhere these could be moved is inside something else, so the honest fix is
to move the *text* rather than shrink the layout: the designators stay on
F.Fab, which is what the assembly drawing is plotted from, and only the
silkscreen loses them. The 220 MOSFET designators, which do fit, stay on
silk so the board is still readable when you are placing parts by hand.

    python relayer-refs.py <board> [ref ...]
"""

import sys

import pcbnew

#: Reference designators whose silk text is unusable at this density.
DEFAULT_REFS = ([f"TP{i}" for i in range(1, 11)]
                + [f"R{i}" for i in range(22, 32)]
                + [f"MH{i}" for i in range(1, 5)])


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    board_path = sys.argv[1]
    want = set(sys.argv[2:]) or set(DEFAULT_REFS)

    board = pcbnew.LoadBoard(board_path)
    moved = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in want:
            continue
        text = fp.Reference()
        if text.GetLayer() == pcbnew.F_Fab:
            continue
        text.SetLayer(pcbnew.F_Fab)
        moved.append(ref)

    print(f"{board_path}: moved {len(moved)} reference field(s) to F.Fab")
    if moved:
        print("  " + ", ".join(sorted(moved)))
    pcbnew.SaveBoard(board_path, board)


if __name__ == "__main__":
    main()
