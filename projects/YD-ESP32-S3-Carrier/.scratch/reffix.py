"""Find silk-clean homes for the six power-section reference designators.

Throwaway.  DRC reports silk_over_copper on C5, C6, C8, R3, R4 and R5: the power
clusters are dense enough that there is no obvious free line to park a ref on,
and the positions in silk.py's fields() table were measured against the parts'
own silk rather than against their copper.

First attempt at this scored candidates by their *bounding box* and found almost
nothing -- which was the tool being wrong, not the board.  KiCad tests the drawn
glyph strokes, not the box around them, and this project sets
min_silk_clearance to 0.0, so only a genuine touch is a violation.  A 2-char ref
at h=1.0 has a 2.20 x 1.70 box but most of that is space between and around the
two glyphs, which is exactly the room the power clusters have to offer.

So candidates are tested with the same primitives DRC uses --
GetEffectiveTextShape() against each item's GetEffectiveShape() -- with a small
margin on top so a passing spot is not merely tangent:

  * copper -- pads and vias.  Those are the items with solder-mask openings, so
              they are the ones silk_over_copper fires on; a track running under
              silk is covered by mask and is not a violation.
  * silk   -- other F.SilkS graphics and other visible ref fields.  silk_overlap
              is enabled and this board is at zero, so it is held to the same
              standard.

Scoring is by Chebyshev distance from the part's own centre, so the winner is
the nearest usable slot rather than the emptiest corner of the window.  Regions
where silk is hidden under a module are rejected outright: text there would pass
DRC and still be unreadable.

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" .scratch/reffix.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

BOARD_W, BOARD_H = 100.0, 64.0

MARGIN = 0.05         # clearance demanded on top of DRC's 0.0
EDGE = 0.30           # keep the text this far inside the board edge
STEP = 0.10

# (ref, search window x0, y0, x1, y1) -- generous but still local to the part.
TARGETS = [
    ("C5", 63.0, 7.0, 72.0, 15.0),
    ("C6", 67.0, 7.0, 76.0, 15.0),
    ("C8", 86.0, 7.0, 96.0, 15.0),
    ("R3", 64.0, 0.0, 73.0, 8.0),
    ("R4", 79.0, 10.0, 88.0, 16.0),
    ("R5", 85.0, 10.0, 94.0, 16.0),
]

# Regions where silkscreen is physically hidden, so text placed there is dead
# ink even when DRC is happy.  These are the *body* extents, not the padded
# keepout boxes: the ES8311 module is 29 x 17 mm and covers (43,15)-(74,32),
# while pour.py's VIA_BAN is that box grown 4 mm taller so no stitching via
# lands under the module's edge.  Using VIA_BAN here would have written off a
# 4 mm band of perfectly visible silk.
HIDDEN = [(43.0, 15.0, 74.0, 32.0),
          (9.7, 6.1, 37.7, 63.3)]


def mm(v):
    return pcbnew.ToMM(v)


def bbox(shape):
    b = shape.BBox()
    return (mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom()))


def near(a, b, pad):
    return not (a[0] > b[2] + pad or b[0] > a[2] + pad
                or a[1] > b[3] + pad or b[1] > a[3] + pad)


def collide(shape, boxes, clearance):
    """Exact shape test, after a cheap box rejection."""
    sb = bbox(shape)
    for bb, other in boxes:
        if near(sb, bb, clearance):
            if shape.Collide(other, pcbnew.FromMM(clearance)):
                return True
    return False


def copper_items(board):
    """Pads and vias with their effective shapes -- what silk_over_copper sees."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            out.append((bbox(p.GetEffectiveShape(pcbnew.F_Cu)),
                        p.GetEffectiveShape(pcbnew.F_Cu)))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            s = t.GetEffectiveShape(pcbnew.F_Cu)
            out.append((bbox(s), s))
    return out


def silk_items(board, skip_ref):
    """Everything on F.SilkS except the field being moved.

    Three sources, and all three are needed: the graphics silk.py draws itself
    (the pin labels and the dev-board outline), the footprints' own library
    silkscreen (J6/J7's connector bodies sit right where the boost cluster's
    refs want to go), and every other footprint's Reference/Value field.
    """
    out = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            s = d.GetEffectiveShape(pcbnew.F_SilkS)
            out.append((bbox(s), s))
    for fp in board.GetFootprints():
        here = str(fp.GetReference()) == skip_ref
        for g in fp.GraphicalItems():
            if g.GetLayer() != pcbnew.F_SilkS:
                continue
            s = g.GetEffectiveShape(pcbnew.F_SilkS)
            out.append((bbox(s), s))
        # Reference() hands back a fresh proxy each call, so identity is no use
        # for skipping the moving field -- take the Value alone when it is ours.
        wanted = [fp.Value()] if here else [fp.Reference(), fp.Value()]
        for f in wanted:
            if not f.IsVisible() or f.GetLayer() != pcbnew.F_SilkS:
                continue
            s = f.GetEffectiveTextShape()
            out.append((bbox(s), s))
    return out


def main():
    board = pcbnew.LoadBoard(BOARD)
    copper = copper_items(board)
    print(f"{len(copper)} pad/via shape(s)")

    for ref, x0, y0, x1, y1 in TARGETS:
        fp = board.FindFootprintByReference(ref)
        f = fp.Reference()
        silk = silk_items(board, ref)

        body = bbox(fp.GetEffectiveShape(pcbnew.F_SilkS))
        cx, cy = (body[0] + body[2]) / 2.0, (body[1] + body[3]) / 2.0

        best = None
        miss = None
        for i in range(int((x1 - x0) / STEP) + 1):
            for j in range(int((y1 - y0) / STEP) + 1):
                x, y = x0 + i * STEP, y0 + j * STEP
                f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
                sh = f.GetEffectiveTextShape()
                b = bbox(sh)
                if (b[0] < EDGE or b[1] < EDGE
                        or b[2] > BOARD_W - EDGE or b[3] > BOARD_H - EDGE):
                    continue
                if any(b[0] < h[2] and h[0] < b[2] and b[1] < h[3] and h[1] < b[3]
                       for h in HIDDEN):
                    continue          # silk there is under a module: dead ink
                bx, by = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
                d = max(abs(bx - cx), abs(by - cy))
                if collide(sh, copper, MARGIN):
                    continue
                if collide(sh, silk, MARGIN):
                    continue
                if best is None or d < best[0]:
                    best = (d, x, y, b, f.GetTextAngleDegrees())

        if best is None:
            print(f"{ref}  NO CLEAN SPOT in the window searched")
            continue
        d, x, y, b, ang = best
        print(f"{ref}  ({x:6.2f}, {y:6.2f})  angle {ang:3.0f}  "
              f"box x {b[0]:6.2f}..{b[2]:6.2f}  y {b[1]:6.2f}..{b[3]:6.2f}  "
              f"d={d:.2f}")


main()
