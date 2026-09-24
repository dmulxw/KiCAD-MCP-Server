"""Silkscreen: pin labels, the dev-board outline, pin-1 markers, zone captions.

The carrier's whole job is to turn a pile of DuPont wires into a plugged-together
sandwich, so the silkscreen has to answer "which hole is GPIO7?" from above,
without a schematic open.  Every header pin therefore gets its signal name, and
the dev board's outline is drawn so the sockets can be lined up before soldering.

Text sizes are chosen against JLCPCB's 0.8 mm minimum character height.  The two
22-pin columns are labelled *outboard* of the dev board (left of J1, right of J2)
because anything between them is hidden under the module once it is plugged in.

Every offset below is set against the *measured* silk extents of the library
footprints, not against their courtyards -- the clearances are 0.2 mm in places
and a courtyard is up to 0.4 mm bigger than the silk inside it.  The script
prints each anchor family it used so a later part move shows up as a stale number.

The script is re-runnable -- it deletes all F.SilkS graphics first.

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" scripts/silk.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

BOARD_W, BOARD_H = 100.0, 64.0

PIN_H = 0.80          # pin label height, mm  (JLCPCB minimum)
PIN_T = 0.15
CAP_H = 1.20          # zone caption height
CAP_T = 0.18
TITLE_H = 1.40        # 16 characters is 22.1 mm at this size, not 19
REF_H = 1.27          # reference designator height

# Dev-board body, from the ESP32-S3 mechanical drawing.
DEV = (9.73, 6.09, 37.67, 63.25)

# --- header rows, top to bottom / left to right ------------------------------
J1 = ["3V3", "3V3", "RST", "IO4", "IO5", "IO6", "IO7", "IO15", "IO16", "IO17",
      "IO18", "IO8", "IO3", "IO46", "IO9", "IO10", "IO11", "IO12", "IO13",
      "IO14", "5V", "GND"]
J2 = ["GND", "IO43", "IO44", "IO1", "IO2", "IO42", "IO41", "IO40", "IO39",
      "IO38", "IO37", "IO36", "IO35", "IO0", "IO45", "IO48", "IO47", "IO21",
      "IO20", "IO19", "GND", "GND"]
J3 = ["SDA", "SCL", "MCK", "BCK", "DI", "WS", "DO", "3V3", "VCC", "GND"]
J4 = ["CS", "DC", "RST", "SDA", "SCK", "VCC", "GND"]
J5 = ["BAT", "GND"]

# The three spare-IO groups.  J6 and J7 carry every pin the dev board leaves
# free on each side; J9 is UART1 on IO17/IO18, which is what the ESP32-S3 routes
# there by default.  IO0/IO46 (strapping), IO19/IO20 (USB D+/-) and IO35-37
# (PSRAM) are deliberately not brought out.
J6 = ["3V3", "GND", "IO9", "IO10", "IO11", "IO12", "IO13", "IO14"]
J7 = ["3V3", "GND", "IO42", "IO39", "IO38", "IO48", "IO43", "IO44"]
J9 = ["IO17", "IO18", "GND"]

# mechanical anchors, mirroring place.py
J1X, J2X, PITCH, ROW0 = 11.00, 36.40, 2.54, 8.00
J3X, J3Y = 46.00, 32.00
J4X, J4Y = 82.00, 31.00
J5X, J5Y = 43.60, 5.40
J6X, J6Y = 76.50, 17.50
J7X, J7Y = 76.50, 26.00
J9X, J9Y = 90.00, 42.00
SWX, SWY = [46.72, 57.72, 68.72, 79.72], 55.77
HOLES = [(4.5, 4.5), (95.5, 4.5), (4.5, 59.5), (95.5, 59.5)]

# How far above/below a horizontal header row a staggered label sits.  Two
# things set the floor: the row's own silk box reaches 1.44 mm either side of
# the pin line (J6/J7 measured), and the connector's *end walls* run the full
# height of that box, so a label only clears them once its own half-height
# (0.73 mm) is past them too.  2.40 leaves 0.23 mm on both counts.
STAG = 2.40

# J3's labels hang downward from the connector. 1.70 clears J3's own silk by
# 0.31 mm and stops 0.30 mm short of C1/C3's silk, which caps the offset from
# above: anything past 1.80 mm runs the 3-character labels into the cap row.
J3_LABEL_DY = 1.70

# Reference designators inside the two power clusters are set smaller than the
# rest. The charge and boost sections are 11 and 16 mm wide with parts stacked
# at five different heights, so there is no clear horizontal band to park a
# 2.2 mm-wide ref in -- most of them fit only because they are 1.0 mm.
PWR_REF_H = 1.00


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def text(board, s, x, y, h=PIN_H, t=PIN_T, angle=0, hj="left", vj="center"):
    o = pcbnew.PCB_TEXT(board)
    o.SetText(s)
    o.SetPosition(vec(x, y))
    o.SetLayer(pcbnew.F_SilkS)
    o.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(h), pcbnew.FromMM(h)))
    o.SetTextThickness(pcbnew.FromMM(t))
    o.SetTextAngleDegrees(angle)
    o.SetHorizJustify({"left": pcbnew.GR_TEXT_H_ALIGN_LEFT,
                       "center": pcbnew.GR_TEXT_H_ALIGN_CENTER,
                       "right": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[hj])
    o.SetVertJustify({"top": pcbnew.GR_TEXT_V_ALIGN_TOP,
                      "center": pcbnew.GR_TEXT_V_ALIGN_CENTER,
                      "bottom": pcbnew.GR_TEXT_V_ALIGN_BOTTOM}[vj])
    board.Add(o)
    return o


def line(board, x1, y1, x2, y2, w=0.15, layer=pcbnew.F_SilkS):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(vec(x1, y1))
    s.SetEnd(vec(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(w))
    board.Add(s)
    return s


def circle(board, cx, cy, r, w=0.15, layer=pcbnew.F_SilkS):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(vec(cx, cy))
    s.SetEnd(vec(cx + r, cy))
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(w))
    board.Add(s)
    return s


def filled_poly(board, pts, w=0.10, layer=pcbnew.F_SilkS):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_POLY)
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    for x, y in pts:
        ps.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    s.SetPolyShape(ps)
    s.SetFilled(True)
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(w))
    board.Add(s)
    return s


HJ = {"left": pcbnew.GR_TEXT_H_ALIGN_LEFT,
      "center": pcbnew.GR_TEXT_H_ALIGN_CENTER,
      "right": pcbnew.GR_TEXT_H_ALIGN_RIGHT}


def ref_field(board, ref, x, y, hj="center", hide=False, h=None, angle=0):
    """Reposition a footprint's Reference text.

    The library footprints park it wherever their own silk is, which lands on
    our pin-1 triangles and captions.  Only ours to move when it would collide,
    but a mislabelled board is worse than a moved reference designator.

    angle=90 is for the power clusters, where parts sit so close along x that
    the only free space is a narrow vertical slot.  A rotated ref wants 1.34 mm
    across and 1.73 mm along, against 1.73 x 1.34 the other way -- which is
    exactly the trade the slots offer.
    """
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        raise SystemExit(f"no footprint {ref}")
    f = fp.Reference()
    f.SetPosition(vec(x, y))
    f.SetTextAngleDegrees(angle)
    f.SetLayer(pcbnew.F_SilkS)
    f.SetVisible(not hide)
    if h is not None:
        f.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(h), pcbnew.FromMM(h)))
        f.SetTextThickness(pcbnew.FromMM(0.15 if h < 1.2 else 0.18))
    f.SetHorizJustify(HJ[hj])
    f.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)


def clear_silk(board):
    """Delete every F.SilkS and F.Fab graphic we may have drawn.

    Proxies are returned, not dropped -- see route.clear_routing() for why
    destroying them under a live board is fatal.
    """
    doomed = [d for d in board.GetDrawings()
              if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.F_Fab)]
    for d in doomed:
        board.Remove(d)
    return doomed


def row_labels(board, names, x0, y):
    """Labels for a *horizontal* header row, staggered either side of it.

    On 2.54 mm pitch a pin gets 2.54 mm, and a 4-character label at 0.8 mm is
    ~2.9 mm wide -- laid out straight they collide.  Rotating them 90 degrees is
    the usual fix (J3 does that), but J6 and J7 have no vertical room for it:
    R4/R5 sit 2.5 mm above J6 and J4's body 2.1 mm below J7.  Alternating above
    and below instead doubles the pitch each label has to clear, and keeps them
    horizontal, which is what makes IO9..IO14 readable at a glance.
    """
    for k, name in enumerate(names):
        dy = -STAG if k % 2 == 0 else STAG
        text(board, name, x0 + k * PITCH, y + dy, hj="center")


def headers(board):
    """Per-pin signal names, outboard of each header so a plugged-in module
    cannot hide them."""
    for k, name in enumerate(J1):
        text(board, name, J1X - 1.70, ROW0 + k * PITCH, hj="right")
    for k, name in enumerate(J2):
        text(board, name, J2X + 1.80, ROW0 + k * PITCH, hj="left")
    # J3 reads bottom-to-top under the connector; 3-char labels on a 2.54 pitch
    # only clear each other when rotated (horizontal ones would collide).
    for k, name in enumerate(J3):
        text(board, name, J3X + k * PITCH, J3Y + J3_LABEL_DY, angle=90, hj="right")
    for k, name in enumerate(J4):
        text(board, name, J4X - 1.90, J4Y + k * PITCH, hj="right")
    # J5 is the one 2-pin header whose labels sit side by side: 'BAT' and 'GND'
    # are 2.54 mm apart but each glyph run is ~2.4 mm wide, so horizontal they
    # cleared each other by 0.12 mm -- below what the fab will hold.  Rotate
    # them like J3, where the pitch runs the other way and only height matters.
    for k, name in enumerate(J5):
        text(board, name, J5X + k * PITCH, J5Y + 2.60, angle=90, hj="right")

    row_labels(board, J6, J6X, J6Y)
    row_labels(board, J7, J7X, J7Y)
    # J9 is only three pins, so it has the room to be read the same way.
    row_labels(board, J9, J9X, J9Y)


def dev_board(board):
    """Outline, pin-1 markers and the USB opening.

    The outline goes on F.Fab, not F.SilkS.  It has to run along x 9.73 and
    37.67, and J1/J2's own silk boxes occupy 9.61-12.39 and 35.01-37.79 -- there
    is simply no free silk there, and a mechanical outline belongs on the
    fabrication layer anyway.  The pin-1 markers stay in silk: those are what
    you actually read while plugging the module in.
    """
    x0, y0, x1, y1 = DEV
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                 ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        line(board, a[0], a[1], b[0], b[1], 0.15, layer=pcbnew.F_Fab)
    for x in (J1X, J2X):
        filled_poly(board, [(x - 0.70, 4.90), (x + 0.70, 4.90), (x, 5.80)])
    text(board, "PIN 1", J1X + 1.60, 5.35, h=0.80, hj="left")

    # The USB socket leaves the dev board at x 19..28 and now stops level with
    # the carrier's bottom edge -- there is no board left below it to draw an
    # arrow on, so the opening is bracketed where it crosses the board instead.
    for tx in (18.50, 29.50):
        line(board, tx, 60.50, tx, 63.50, 0.20)
    text(board, "USB", 24.00, 61.00, h=1.00, t=CAP_T, hj="center")


def fields(board):
    """Move the reference designators that land on our own silk.

    Every x/y below is a measured clearance against the part's own silkscreen --
    see .scratch/silkbox.py, which prints those extents off the board.  The
    power section is the crowded part: the charge cluster is 11 mm wide and the
    boost cluster 16, so those refs fan out to whichever side of their own body
    is free rather than sitting on a common line.

    H1-H4's refs are hidden outright.  The Ø3.2 holes are marked by the 'M3'
    ring and caption in captions(), and the library parks the designator at
    y 0.35, which at a 4.5 mm inset is off the edge of the board.
    """
    # (ref, x, y, horizontal justify, height, angle).  The rotated entries are
    # the ones whose only free space is a vertical slot between two neighbours.
    for ref, x, y, hj, h, ang in (
            ("J1", J1X, 3.40, "center", REF_H, 0),
            ("J2", J2X, 3.40, "center", REF_H, 0),
            ("J3", 44.93, 29.20, "center", REF_H, 0),
            ("J4", 84.80, 31.00, "left", REF_H, 0),
            ("J5", 49.00, 5.40, "left", REF_H, 0),
            ("J6", 74.12, 17.50, "right", REF_H, 0),
            ("J7", 74.12, 26.00, "right", REF_H, 0),
            ("J9", 87.62, 42.00, "right", REF_H, 0),
            ("SW5", 59.00, 2.80, "center", REF_H, 0),
            # charge cluster: U1's silk starts at x 64.34 and SW5's ends at
            # 61.47, so U1/R2 go in the 3.31 mm channel left of the IC.
            #
            # C5, C6 and R3 sit in the cluster's *side* gaps.  Nothing may hang
            # below them: the ES8311 module is 29 x 17 mm on J3 and covers
            # (43,15)-(74,32), so the band it hides starts at y 15, not at the
            # y 11 that pour.py's VIA_BAN box suggests -- that box is the module
            # outline grown 4 mm taller so no stitching via lands under its rim.
            # C5 uses that 4 mm band, which is the last silk-visible space below
            # the charge cluster; C6 and R3 go beside their parts.
            ("U1", 63.20, 6.20, "center", PWR_REF_H, 90),
            ("R2", 63.20, 1.90, "center", PWR_REF_H, 90),
            ("R3", 71.40, 3.60, "center", PWR_REF_H, 90),
            ("D3", 73.20, 4.10, "center", REF_H, 0),
            ("C5", 63.20, 11.60, "left", PWR_REF_H, 0),
            ("C6", 71.20, 8.50, "left", PWR_REF_H, 0),
            # boost cluster: same story -- C8 sits in the gap between U2 and
            # itself, R4/R5 in the free channel at y 13.6-14.2 between their own
            # bodies and J6's staggered pin labels, which start at y 14.7.
            ("C7", 77.55, 12.60, "center", REF_H, 0),
            ("L1", 80.60, 3.00, "center", REF_H, 0),
            ("D2", 86.70, 1.90, "center", REF_H, 0),
            ("U2", 86.10, 8.10, "left", PWR_REF_H, 0),
            ("C8", 89.70, 8.60, "left", PWR_REF_H, 0),
            ("R4", 83.20, 14.50, "center", PWR_REF_H, 90),
            ("R5", 89.20, 14.40, "center", PWR_REF_H, 90),
            ("C1", 45.275, 47.50, "center", REF_H, 0),
            ("C2", 50.075, 47.50, "center", REF_H, 0),
            ("C3", 54.875, 47.50, "center", REF_H, 0),
            ("C4", 59.675, 47.50, "center", REF_H, 0),
            ("D1", 64.935, 47.50, "center", REF_H, 0),
            ("R1", 70.195, 47.50, "center", REF_H, 0)):
        ref_field(board, ref, x, y, hj=hj, h=h, angle=ang)
    # The button designators sit *above* their switches, not between the body and
    # the cap row.  At y 51.00 a 1.27 mm ref spans 50.275..51.725 and the top pads
    # start at 51.50 -- a 0.225 mm bite out of every one of the four, which DRC
    # reported four times.  y 49.90 puts the box at 49.175..50.625: 0.875 mm clear
    # of the pads and 0.95 mm clear of the C1..R1 row's refs at 47.50.
    for k, cx in enumerate(SWX):
        ref_field(board, f"SW{k + 1}", cx - 3.28, 49.90, hj="left", h=REF_H)
    for ref in ("H1", "H2", "H3", "H4"):
        ref_field(board, ref, 0.0, 0.0, hide=True)


def captions(board):
    """Zone captions, button face names, hole rings and the board title.

    The bottom band is shared three ways: button names at y 61.0, the title at
    62.7, and the M3 rings at 59.5 with their own caption at 62.8.  The title is
    16 characters -- 22.1 mm at this size, against 25.3 mm before -- so it is
    centred at x 53 and still clears J2's column by 4.2 mm on the left and the
    M3 caption by 30 mm on the right.
    """
    text(board, "LANFENG-ESP32-S3", 53.00, 62.70, h=TITLE_H, t=CAP_T, hj="center")

    # Clear of the ES8311 module's flat area, which starts at y 11 and would
    # hide anything printed below it.  AUDIO moved up 0.3 mm from 31.2: at the
    # larger caption height its box reached y 32.10, which is 0.17 mm off
    # ES8311's box top at 32.27 -- under the 0.20 mm the fab will hold.
    text(board, "AUDIO", J3X + 24.60, 30.90, h=1.00, t=CAP_T, hj="left")
    text(board, "ES8311", J3X + 24.60, 33.00, h=0.80, hj="left")
    # J4's body fills x 80.56-83.44 down to y 47.68, so TFT goes underneath it --
    # but SW4's designator ends at x 80.60 in the same band, which cost the
    # caption 0.077 mm of overlap when it was centred.  Nudged 0.6 mm right.
    text(board, "TFT", J4X + 0.60, 49.00, h=CAP_H, t=CAP_T, hj="center")
    text(board, "PWR SW", 53.00, 2.40, h=1.00, t=CAP_T, hj="center")
    text(board, "BAT 3.7V", 41.50, 2.40, h=1.00, t=CAP_T, hj="center")
    text(board, "SPARE IO", 74.50, 21.75, h=1.00, t=CAP_T, hj="right")
    text(board, "UART", J9X + PITCH * 1.5, 37.60, h=1.00, t=CAP_T, hj="center")

    # y 61.00, not 60.40: the switch pads reach down to y 60.00 and a 0.90 mm
    # label at 60.40 spans 59.86..60.94, so 'VOL+', 'VOL-' and 'RESET' each cut
    # into the pads below them.  The window is narrow -- 60.84 is the first y that
    # clears the pads by 0.30 and 61.17 the last that clears the title's box top
    # at 61.91 -- so 61.00 is deliberately mid-channel.
    for cx, s in zip(SWX, ("VOL+", "VOL-", "ACT", "RESET")):
        text(board, s, cx, 61.00, h=0.90, t=CAP_T, hj="center")

    for cx, cy in HOLES:
        # r 2.00, not the 2.20 of v1.  The holes moved in to a 4.5 mm inset, and
        # H3's ring at 2.20 then came 0.075 mm from the corner of J1's pin-22
        # 'GND' label -- the one place on the board where the two are neighbours.
        # At 2.00 the ring's outer edge is 2.075 mm from the hole centre, which
        # leaves 0.33 mm of bare board around the Ø3.2 hole and 0.27 mm to that
        # label: both clear, and the ring still reads as a hole marker.
        circle(board, cx, cy, 2.00, 0.15)
        text(board, "M3", cx, cy + 3.30, h=0.90, hj="center")


def main():
    board = pcbnew.LoadBoard(BOARD)
    _keep_alive = clear_silk(board)   # noqa: F841
    headers(board)
    dev_board(board)
    captions(board)
    fields(board)
    board.Save(BOARD)
    draw = board.GetDrawings()
    silk = len([d for d in draw if d.GetLayer() == pcbnew.F_SilkS])
    fab = len([d for d in draw if d.GetLayer() == pcbnew.F_Fab])
    pins = sum(len(g) for g in (J1, J2, J3, J4, J5, J6, J7, J9))
    print(f"F.SilkS: {silk} graphic(s), F.Fab: {fab} -- {pins} pin labels + "
          f"markers/captions, dev outline on Fab")
    print(f"staggered rows J6/J7/J9 at +/-{STAG} mm")
    print("saved", BOARD)


main()
