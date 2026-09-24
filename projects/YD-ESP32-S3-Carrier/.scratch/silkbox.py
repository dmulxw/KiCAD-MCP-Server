"""Silkscreen bounding boxes of the footprints silk.py has to lay out around.

Every position in silk.py is chosen so our text clears the part's own silk.  The
library footprints' extents are not something to guess at -- read them off the
board, put them on F.Fab, and then place against real numbers.
"""
import importlib.util

import pcbnew

spec = importlib.util.spec_from_file_location(
    "place", r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\scripts\place.py")

board = pcbnew.LoadBoard(
    r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb")

REFS = ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J9",
        "SW1", "SW2", "SW3", "SW4", "SW5",
        "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
        "D1", "D2", "D3", "R1", "R2", "R3", "R4", "R5", "L1", "U1", "U2",
        "H1", "H2", "H3", "H4"]


def mm(v):
    return pcbnew.ToMM(v)


print(f"{'ref':<5} {'silk x0..x1':>20} {'silk y0..y1':>20} {'all x0..x1':>20} {'all y0..y1':>20}")
for ref in REFS:
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        print(f"{ref:<5}  -- not on board --")
        continue

    # silk only: walk the footprint's own graphics
    sx0 = sy0 = 1e9
    sx1 = sy1 = -1e9
    for g in fp.GraphicalItems():
        if g.GetLayer() != pcbnew.F_SilkS:
            continue
        b = g.GetBoundingBox()
        sx0, sy0 = min(sx0, mm(b.GetLeft())), min(sy0, mm(b.GetTop()))
        sx1, sy1 = max(sx1, mm(b.GetRight())), max(sy1, mm(b.GetBottom()))

    b = fp.GetBoundingBox(False, False)
    ax0, ay0, ax1, ay1 = mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom())

    s = (f"{sx0:8.2f}..{sx1:<8.2f}" if sx0 < 1e8 else "     none          ")
    print(f"{ref:<5} {s:>20} {f'{sy0:8.2f}..{sy1:<8.2f}' if sx0 < 1e8 else '':>20} "
          f"{ax0:8.2f}..{ax1:<8.2f} {ay0:8.2f}..{ay1:<8.2f}")

    # the Reference field's own position, since that is what silk.py moves
    f = fp.Reference()
    p = f.GetPosition()
    print(f"      ref field at ({mm(p.x):.2f}, {mm(p.y):.2f})  "
          f"text='{f.GetText()}'  visible={f.IsVisible()}")
