"""Silkscreen collision check -- the class of error KiCad's DRC cannot see.

DRC checks silk against *pads and mask openings*.  It does not check silk text
against another footprint's silk box, nor one footprint's field against another
footprint's field.  On a board where the whole point of the silk is 82 pin
labels, that is exactly the collision that matters, so it gets its own pass.

Every F.SilkS item is collected -- our drawing shapes, our texts, the footprints'
own graphics, and their Reference/Value fields -- and each pair is tested with
the axis-aligned bounding box KiCad itself computes.  A bbox is conservative for
rotated text (it is the box of the rotated glyph run, not of the glyphs), so a
reported pair is a candidate: read the numbers, they are in mm.

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" .scratch/silkchek.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

# Two silk items closer than this are flagged.  The fab asks for 0.2 mm of silk
# to silk; below that the second item is what disappears.
MIN_GAP = 0.20


def mm(v):
    return pcbnew.ToMM(v)


def box(item):
    b = item.GetBoundingBox()
    return (mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom()))


def name_of(item):
    """Name an item for the report -- class names moved between KiCad versions
    (FP_TEXT is gone in 10), so identify by what the item can answer instead."""
    if hasattr(item, "GetText"):
        return str(item.GetText())
    if hasattr(item, "GetShape"):
        return {pcbnew.SHAPE_T_SEGMENT: "line",
                pcbnew.SHAPE_T_CIRCLE: "circle",
                pcbnew.SHAPE_T_POLY: "poly"}.get(item.GetShape(), "shape")
    return "item"


def gap(a, b):
    """Signed separation of two bboxes: >0 means clear, <0 means overlap."""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx <= 0 and dy <= 0:                      # boxes intersect
        return max(dx, dy)
    return max(dx, dy, 0.0) if (dx > 0 or dy > 0) else 0.0


def main():
    board = pcbnew.LoadBoard(BOARD)

    # Owner is carried alongside the name so a footprint's own silk crossing its
    # own outline -- which every cap and diode does -- can be skipped.  Only
    # *between* owners does silk collide in a way that matters.
    items = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            items.append(("board", f"board:{name_of(d)}", box(d)))
    for fp in board.GetFootprints():
        ref = str(fp.GetReference())
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS:
                items.append((ref, f"{ref}:{name_of(g)}", box(g)))
        for f in (fp.Reference(), fp.Value()):
            if f.IsVisible() and f.GetLayer() == pcbnew.F_SilkS:
                items.append((ref, f"{ref}:{f.GetText()}", box(f)))

    print(f"{len(items)} F.SilkS item(s)\n")
    bad = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            oa, na, a = items[i]
            ob, nb, b = items[j]
            if oa == ob:
                continue
            g = gap(a, b)
            if g < MIN_GAP:
                bad.append((g, na, nb, a, b))

    for g, na, nb, a, b in sorted(bad, key=lambda r: r[0]):
        print(f"  gap {g:7.3f}  {na:<22} {nb}")
        print(f"             A x {a[0]:7.2f}..{a[2]:<7.2f} y {a[1]:7.2f}..{a[3]:<7.2f}")
        print(f"             B x {b[0]:7.2f}..{b[2]:<7.2f} y {b[1]:7.2f}..{b[3]:<7.2f}")

    print(f"\n{len(bad)} pair(s) under {MIN_GAP} mm")


main()
