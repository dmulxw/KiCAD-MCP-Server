"""Self-checks: header grid vs the mechanical drawing, mounting holes, keep-out
zones, silkscreen collisions, and the v2 power section.

Run:  "C:/Program Files/KiCad/10.0/bin/python.exe" scripts/verify_geometry.py
"""
import math

import pcbnew

BOARD = r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier\YD-ESP32-S3-Carrier.kicad_pcb"
BOARD_W, BOARD_H = 100.0, 64.0
board = pcbnew.LoadBoard(BOARD)
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}


def padxy(ref, num, idx=0):
    hits = [p for p in fps[ref].Pads() if str(p.GetNumber()) == str(num)]
    p = hits[idx]
    return pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)


fails = []


def check(label, got, want, tol=0.01):
    ok = abs(got - want) <= tol
    print(f"  [{'OK ' if ok else 'FAIL'}] {label:<46} got={got:8.3f}  want={want:8.3f}")
    if not ok:
        fails.append(label)


def bbox(ref, margin=0.0):
    bb = fps[ref].GetBoundingBox(False, False)
    return (pcbnew.ToMM(bb.GetLeft()) - margin, pcbnew.ToMM(bb.GetTop()) - margin,
            pcbnew.ToMM(bb.GetRight()) + margin, pcbnew.ToMM(bb.GetBottom()) + margin)


def bb_of(o):
    """Bounding box of any board item, in mm."""
    b = o.GetBoundingBox()
    return (pcbnew.ToMM(b.GetLeft()), pcbnew.ToMM(b.GetTop()),
            pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))


def overlaps(a, b, slack=0.0):
    return not (a[2] <= b[0] + slack or b[2] <= a[0] + slack or
                a[3] <= b[1] + slack or b[3] <= a[1] + slack)


print("== J1 / J2 header grid vs ESP32-S3 mechanical drawing ==")
c1x, c1y = padxy("J1", 1)
c2x, c2y = padxy("J2", 1)
check("column spacing (J2.pad1.x - J1.pad1.x)", c2x - c1x, 25.40)
check("pin-1 rows aligned (J1.pad1.y - J2.pad1.y)", c1y - c2y, 0.00)
check("J1 pin1 x", c1x, 11.00)
check("J1 pin1 y", c1y, 8.00)
check("J1 pitch (pad2 - pad1)", padxy("J1", 2)[1] - c1y, 2.54)
check("J1 span pin1->pin22", padxy("J1", 22)[1] - c1y, 53.34)
check("J2 span pin1->pin22", padxy("J2", 22)[1] - c2y, 53.34)
check("J1/J2 pads in same row at pin 22", padxy("J1", 22)[1] - padxy("J2", 22)[1], 0.00)

print("\n== module headers ==")
j3a, j3b = padxy("J3", 1), padxy("J3", 10)
check("J3 horizontal (pad1.y == pad10.y)", j3a[1] - j3b[1], 0.00)
check("J3 pitch", padxy("J3", 2)[0] - j3a[0], 2.54)
check("J3 span pin1->pin10", j3b[0] - j3a[0], 22.86)
j5a, j5b = padxy("J5", 1), padxy("J5", 2)
check("J5 horizontal", j5a[1] - j5b[1], 0.00)
check("J5 pitch", j5b[0] - j5a[0], 2.54)
check("J4 span pin1->pin7", padxy("J4", 7)[1] - padxy("J4", 1)[1], 15.24)
# The three spare-IO groups: 2.54 pitch on each, and the two 1x8 rows parallel to
# each other so a ribbon or a pair of jumpers lands square.
check("J6 span pin1->pin8", padxy("J6", 8)[0] - padxy("J6", 1)[0], 17.78)
check("J7 span pin1->pin8", padxy("J7", 8)[0] - padxy("J7", 1)[0], 17.78)
check("J6/J7 pin1 x aligned", padxy("J6", 1)[0] - padxy("J7", 1)[0], 0.00)
check("J6/J7 horizontal (pad1.y == pad8.y)",
      padxy("J6", 1)[1] - padxy("J6", 8)[1], 0.00)
check("J9 span pin1->pin3", padxy("J9", 3)[0] - padxy("J9", 1)[0], 5.08)

print("\n== mounting holes: Ø3.2 NPTH, inset 4.5 from each corner ==")
for ref, (hx, hy) in {"H1": (4.5, 4.5), "H2": (95.5, 4.5),
                      "H3": (4.5, 59.5), "H4": (95.5, 59.5)}.items():
    pads = list(fps[ref].Pads())
    p = pads[0]
    x, y = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    drill = pcbnew.ToMM(p.GetDrillSize().x)
    check(f"{ref} centre x", x, hx)
    check(f"{ref} centre y", y, hy)
    check(f"{ref} drill Ø", drill, 3.20, 0.001)
    check(f"{ref} size == drill (no annular ring)", pcbnew.ToMM(p.GetSize().x), 3.20, 0.001)
    ok = p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
    print(f"  [{'OK ' if ok else 'FAIL'}] {ref} is NPTH (no copper)                   "
          f"attr={p.GetAttribute()}")
    if not ok:
        fails.append(f"{ref} NPTH")

print("\n== mounting-hole keep-out: nothing within 4 mm of a hole centre ==")
hole_boxes = []
for ref in ("H1", "H2", "H3", "H4"):
    p = list(fps[ref].Pads())[0]
    cx, cy = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    hole_boxes.append((ref, (cx - 4.0, cy - 4.0, cx + 4.0, cy + 4.0)))
for ref in sorted(fps):
    if ref.startswith("H"):
        continue
    bb = bbox(ref)
    for hname, hb in hole_boxes:
        if overlaps(bb, hb):
            print(f"  [FAIL] {ref} bbox {tuple(round(v,1) for v in bb)} "
                  f"enters {hname} keep-out {hb}")
            fails.append(f"{ref} into {hname}")
print(f"  checked {len(fps)-4} components against 4 holes")

# The ES8311 module is 29 x 17 mm and plugs into J3 (pads at y 32.00), so its
# body lies over y 15..32 -- measured, not guessed.  pour.py and route.py ban
# vias over y 11..32 instead, which is this box plus a 4 mm hat; the hat is
# deliberate slack for the through-hole pins' own length, and C5/C6 legitimately
# sit in it (their bodies stop at y 11.17), so components are tested against the
# real body and vias against the padded ban.
FLAT_LAY = (43.0, 15.0, 74.0, 32.0)
VIA_BAN = ((43.0, 11.0, 74.0, 32.0), (18.0, 60.0, 29.0, 64.0))

print(f"\n== audio module flat-lay zone {FLAT_LAY} must hold only J3 ==")
for ref in sorted(fps):
    if ref == "J3":
        continue
    bb = bbox(ref)
    if overlaps(bb, FLAT_LAY):
        print(f"  [FAIL] {ref} bbox {tuple(round(v,1) for v in bb)} sits in the flat-lay zone")
        fails.append(f"{ref} in flat-lay zone")
print("  scanned all components except J3")

print("\n== USB overhang zone (x 18..29, y 60..64) must be empty ==")
usb = (18.0, 60.0, 29.0, 64.0)
for ref in sorted(fps):
    bb = bbox(ref)
    if overlaps(bb, usb):
        print(f"  [FAIL] {ref} bbox {tuple(round(v,1) for v in bb)} sits under the USB plug")
        fails.append(f"{ref} in USB zone")
print("  scanned all components")

print("\n== component-to-component courtyard gaps (bbox approximation) ==")
refs = sorted(fps)
for i, a in enumerate(refs):
    for b in refs[i + 1:]:
        if overlaps(bbox(a), bbox(b)):
            print(f"  [FAIL] {a} overlaps {b}")
            fails.append(f"{a}/{b} overlap")
print(f"  checked all {len(refs)*(len(refs)-1)//2} pairs")

print(f"\n== everything inside the {BOARD_W:.0f} x {BOARD_H:.0f} board outline ==")
for ref in refs:
    bb = bbox(ref)
    if (bb[0] < -0.01 or bb[1] < -0.01
            or bb[2] > BOARD_W + 0.01 or bb[3] > BOARD_H + 0.01):
        print(f"  [FAIL] {ref} bbox {tuple(round(v,1) for v in bb)} leaves the board")
        fails.append(f"{ref} off board")
print("  scanned all components")

print("\n== via-free zones: the audio module and the USB plug must lie flat ==")
print("  (route.py skips GND entirely and pour.py bans its own stitching lattice")
print("   here, so a via in either box means one of the two scripts mis-placed one)")
for z in VIA_BAN:
    name = f"(x {z[0]:.0f}..{z[2]:.0f}, y {z[1]:.0f}..{z[3]:.0f})"
    n = 0
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        p = t.GetPosition()
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        if z[0] <= x <= z[2] and z[1] <= y <= z[3]:
            n += 1
            print(f"  [FAIL] {t.GetNetname()} via at ({x:.2f},{y:.2f}) in {name}")
            fails.append(f"via {t.GetNetname()} @({x:.0f},{y:.0f}) in {name}")
    if n == 0:
        print(f"  [OK ] no vias in {name}")

print("\n== copper pull-back around H1-H4 (hole r=1.6, keep-out r=2.7 -> 1.1 mm) ==")
PULLBACK = 1.10
HOLE_R = 1.60
for ref in ("H1", "H2", "H3", "H4"):
    p = list(fps[ref].Pads())[0]
    hx, hy = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)

    # nothing routed within the keep-out
    near = []
    for t in board.GetTracks():
        pp = t.GetPosition()
        if t.GetClass() == "PCB_VIA":
            d = ((pcbnew.ToMM(pp.x) - hx) ** 2 + (pcbnew.ToMM(pp.y) - hy) ** 2) ** 0.5
        else:
            s, e = t.GetStart(), t.GetEnd()
            x1, y1 = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
            x2, y2 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
            dx, dy = x2 - x1, y2 - y1
            l2 = dx * dx + dy * dy
            u = 0.0 if l2 == 0 else max(0.0, min(1.0, ((hx - x1) * dx + (hy - y1) * dy) / l2))
            d = ((hx - (x1 + u * dx)) ** 2 + (hy - (y1 + u * dy)) ** 2) ** 0.5
        if d < HOLE_R + PULLBACK:
            near.append(f"{t.GetNetname()}@{d:.2f}")
    # and no poured copper either
    poured = []
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        lset = zone.GetLayerSet()
        # GetFilledPolysList() asserts on a layer the zone does not occupy, and
        # each of our pours is single-layer -- so ask only for its own layers.
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not lset.Contains(layer):
                continue
            poly = zone.GetFilledPolysList(layer)
            for k in range(24):
                a = k * 3.14159265 / 12.0
                for rr in (HOLE_R + 0.10, HOLE_R + 0.55, HOLE_R + 1.00):
                    pt = pcbnew.VECTOR2I(pcbnew.FromMM(hx + rr * math.cos(a)),
                                         pcbnew.FromMM(hy + rr * math.sin(a)))
                    if poly.Contains(pt):
                        poured.append(f"{rr:.2f}mm")
                        break
    ok = not near and not poured
    detail = (f"tracks={near}" if near else "") + (f"pour_at={sorted(set(poured))}" if poured else "")
    print(f"  [{'OK ' if ok else 'FAIL'}] {ref} clear of copper                       {detail}")
    if not ok:
        fails.append(f"{ref} copper too close")

print("\n== silkscreen: every pair of items that do not belong to the same part ==")
print("  (KiCad's DRC tests silk-over-copper, and silk graphics against silk")
print("   graphics, but NOT text against a footprint's own arcs/lines, and NOT")
print("   one footprint's field against another's -- both were live defects here)")
#
# Every item carries an *owner*.  A footprint's graphics and its visible fields
# share that footprint's reference, so a cap's own silk crossing its own outline
# -- which every cap and diode does by design -- never gets reported.  Board-level
# drawings each get a unique owner instead of one shared "board" tag: a caption
# clipping a pin label is exactly the defect this pass exists to catch, and those
# are both ours.
MIN_GAP = 0.20        # the fab's silk-to-silk minimum; below it, one item vanishes


def shape_of(o):
    """The item's real outline, text or graphic.

    The check below used to compare bounding boxes, with a special case for
    circles.  Both were the same mistake in different clothes: a box is not what
    the item is.  A Ø4.4 ring does not fill its box, and neither does a 2-char
    designator -- 'R5' at h=1.00 has a 2.20 x 1.70 box, but the strokes inside it
    are two glyphs with clear space above and below, which is exactly where a
    crowded board has room to put things.

    Measuring the box made the title block and the button captions look like they
    collide when their glyphs are 0.5 mm apart, and it wanted a caption row that
    does not fit between the switch pads and the title on a 64 mm board.  The
    check is still stricter than DRC -- it demands MIN_GAP of real clearance
    where the project sets min_silk_clearance to 0.0 -- it just measures the
    clearance that exists.
    """
    if hasattr(o, "GetText"):
        return o.GetEffectiveTextShape()
    return o.GetEffectiveShape(pcbnew.F_SilkS)


def name_of(o):
    """Name an item for the report.  Class names moved between KiCad versions
    (FP_TEXT is gone in 10), so identify by what the item can answer instead."""
    if hasattr(o, "GetText"):
        t = str(o.GetText())
        return repr(t) if len(t) <= 12 else repr(t[:11] + "..")
    if hasattr(o, "GetShape"):
        return {pcbnew.SHAPE_T_SEGMENT: "line", pcbnew.SHAPE_T_CIRCLE: "circle",
                pcbnew.SHAPE_T_POLY: "poly", pcbnew.SHAPE_T_RECT: "rect"}.get(
                    o.GetShape(), "shape")
    return "item"


def sep(a, b):
    """Clearance in mm between two silk items; negative when they overlap.

    Bisection on SHAPE::Collide, so the answer is in the same units KiCad's own
    clearance tests use.  Collide() answers yes/no rather than how far, so the
    gap is found by halving an interval that is comfortably wider than any silk
    gap on this board; ten steps resolve it to 0.002 mm, far below MIN_GAP.
    """
    sa, sb = a[3], b[3]
    if not sa.Collide(sb, 0):
        lo, hi = 0.0, 2.0
        for _ in range(10):
            mid = (lo + hi) / 2.0
            if sa.Collide(sb, pcbnew.FromMM(mid)):
                hi = mid
            else:
                lo = mid
        return lo
    # They genuinely touch.  Collide() does not report penetration depth, so
    # there is no honest millimetre figure to give -- a small negative marks it
    # as an overlap without pretending to measure how much.
    return -0.001


silk = []            # (owner, label, bbox, shape); bbox is the broad phase only
for i, d in enumerate(board.GetDrawings()):
    if d.GetLayer() == pcbnew.F_SilkS:
        silk.append((f"board#{i}", f"board:{name_of(d)}", bb_of(d), shape_of(d)))
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS:
            silk.append((ref, f"{ref}:{name_of(g)}", bb_of(g), shape_of(g)))
    for f in fp.GetFields():
        if f.IsVisible() and f.GetLayer() == pcbnew.F_SilkS:
            silk.append((ref, f"{ref}.{f.GetName()}", bb_of(f), shape_of(f)))

# Two items further apart than this cannot be within MIN_GAP, and skipping them
# on their boxes keeps the exact test off the ~5700 pairs that are nowhere near
# each other.  It has to be wider than sep()'s 2 mm bisection bound or a real
# clash could be filtered out before it is ever measured.
BROAD = 2.0 + MIN_GAP


def box_gap(a, b):
    """Axis-wise separation of two bboxes; negative when they overlap."""
    return max(max(a[0] - b[2], a[2] - b[0]), max(a[1] - b[3], a[3] - b[1]))


clash = 0
worst = []
for i in range(len(silk)):
    for j in range(i + 1, len(silk)):
        if silk[i][0] == silk[j][0]:
            continue
        if box_gap(silk[i][2], silk[j][2]) > BROAD:
            continue
        g = sep(silk[i], silk[j])
        if g < MIN_GAP:
            clash += 1
            if len(worst) < 20:
                worst.append((g, silk[i], silk[j]))
for g, a, b in sorted(worst, key=lambda r: r[0]):
    print(f"  [FAIL] gap {g:7.3f}  {a[1]:<22} {b[1]}")
    print(f"                       A x {a[2][0]:7.2f}..{a[2][2]:<7.2f} "
          f"y {a[2][1]:7.2f}..{a[2][3]:<7.2f}")
    print(f"                       B x {b[2][0]:7.2f}..{b[2][2]:<7.2f} "
          f"y {b[2][1]:7.2f}..{b[2][3]:<7.2f}")
if clash:
    fails.append(f"{clash} silk pair(s) under {MIN_GAP} mm")
print(f"  checked {len(silk)} F.SilkS item(s) pairwise  -- "
      + (f"{clash} pair(s) under {MIN_GAP} mm" if clash else "all clear"))

print("\n== every header pin: printed label vs the net the schematic assigns ==")
print("  (labels live in silk.py, nets come from the schematic, and this table is")
print("   transcribed from 声音模块与显示模块和ESP32S3开发模块连接.pdf -- three")
print("   independent records.  Any one drifting from the other two is caught, and")
print("   a board wired right but labelled wrong is worse than one that won't boot)")
#
# Two different labelling conventions, both deliberate:
#   J1/J2 are the ESP32-S3's own sockets, so they print the *GPIO number* --
#     that is what you read while plugging the dev board in.  The wiring PDF
#     supplies the pairing, e.g. I2S_MCK is on GPIO3.
#   J3/J4 are module sockets, so they print the *module's* pin name -- 'VCC'
#     and 'SDA' are what is written on the ES8311 and the TFT boards themselves.
#   J6/J7/J9 print the GPIO number too: they are for whatever the user wires up
#     next, and the dev board's own silkscreen is the reference they will read.
#   J5-1 is labelled 'BAT' because that is what it is -- the raw 3.7 V cell, on
#     the battery side of SW5.  In v1 this pin printed '+5V' and sat directly on
#     the 5 V rail; v2 puts the boost between them, so the label had to change.
PIN_TABLE = {
    "J1": [(1, "3V3", "+3V3"), (2, "3V3", "+3V3"), (3, "RST", "BTN_RST"),
           (4, "IO4", "BTN_VOL_UP"), (5, "IO5", "BTN_VOL_DN"), (6, "IO6", "I2S_DO"),
           (7, "IO7", "I2S_DI"), (8, "IO15", "I2S_BCK"), (9, "IO16", "I2S_WS"),
           (10, "IO17", "IO17"), (11, "IO18", "IO18"), (12, "IO8", "BTN_ACT"),
           (13, "IO3", "I2S_MCK"), (14, "IO46", ""), (15, "IO9", "IO9"),
           (16, "IO10", "IO10"), (17, "IO11", "IO11"), (18, "IO12", "IO12"),
           (19, "IO13", "IO13"), (20, "IO14", "IO14"), (21, "5V", "+5V"),
           (22, "GND", "GND")],
    "J2": [(1, "GND", "GND"), (2, "IO43", "IO43"), (3, "IO44", "IO44"),
           (4, "IO1", "I2C_SDA"), (5, "IO2", "I2C_SCL"), (6, "IO42", "IO42"),
           (7, "IO41", "LCD_CS"), (8, "IO40", "LCD_DC"), (9, "IO39", "IO39"),
           (10, "IO38", "IO38"), (11, "IO37", ""), (12, "IO36", ""),
           (13, "IO35", ""), (14, "IO0", ""), (15, "IO45", "LCD_RST"),
           (16, "IO48", "IO48"), (17, "IO47", "LCD_SDA"), (18, "IO21", "LCD_SCK"),
           (19, "IO20", ""), (20, "IO19", ""), (21, "GND", "GND"), (22, "GND", "GND")],
    "J3": [(1, "SDA", "I2C_SDA"), (2, "SCL", "I2C_SCL"), (3, "MCK", "I2S_MCK"),
           (4, "BCK", "I2S_BCK"), (5, "DI", "I2S_DI"), (6, "WS", "I2S_WS"),
           (7, "DO", "I2S_DO"), (8, "3V3", "+3V3"), (9, "VCC", "+5V"),
           (10, "GND", "GND")],
    "J4": [(1, "CS", "LCD_CS"), (2, "DC", "LCD_DC"), (3, "RST", "LCD_RST"),
           (4, "SDA", "LCD_SDA"), (5, "SCK", "LCD_SCK"), (6, "VCC", "+3V3"),
           (7, "GND", "GND")],
    "J5": [(1, "BAT", "VBAT"), (2, "GND", "GND")],
    # The three spare groups.  Each GPIO is brought out exactly once -- a second
    # header on the same pin would be a trap, not a convenience.
    "J6": [(1, "3V3", "+3V3"), (2, "GND", "GND"), (3, "IO9", "IO9"),
           (4, "IO10", "IO10"), (5, "IO11", "IO11"), (6, "IO12", "IO12"),
           (7, "IO13", "IO13"), (8, "IO14", "IO14")],
    "J7": [(1, "3V3", "+3V3"), (2, "GND", "GND"), (3, "IO42", "IO42"),
           (4, "IO39", "IO39"), (5, "IO38", "IO38"), (6, "IO48", "IO48"),
           (7, "IO43", "IO43"), (8, "IO44", "IO44")],
    "J9": [(1, "IO17", "IO17"), (2, "IO18", "IO18"), (3, "GND", "GND")],
}

# Two subtleties, both of which produced false alarms before being pinned down:
#   * distance is to a text's *extent*, not its anchor -- 'AUDIO' is a caption
#     whose anchor happens to sit nearer J3.10 than that pin's own 'GND' does;
#   * only the connector's *own* labels are allowed to compete for its pins, so
#     a nearby caption cannot be mistaken for one.  J3's and J5's labels are
#     rotated and sit 1.7-2.6 mm from their pads, which puts 'AUDIO' and 'BAT
#     3.7V' nearer than the real thing.
labels = []
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.F_SilkS and d.GetClass() == "PCB_TEXT":
        labels.append((d.GetText(), bb_of(d)))


def gap_to(r, px, py):
    dx = max(r[0] - px, 0.0, px - r[2])
    dy = max(r[1] - py, 0.0, py - r[3])
    return math.hypot(dx, dy)


# Widest real offset is 2.60 mm: J5's rotated labels, which clear their pads by
# that much because the pin line runs the other way.  J6/J7/J9's staggered rows
# are the next worst at 2.40 mm.
MAX_GAP = 3.0
bad = checked = 0
for ref, table in PIN_TABLE.items():
    own = {lbl for _, lbl, _ in table}
    cands = [(t, r) for t, r in labels if t in own]
    for pin, label, net in table:
        hits = [p for p in fps[ref].Pads() if str(p.GetNumber()) == str(pin)]
        if len(hits) != 1:
            print(f"  [FAIL] {ref}.{pin}: {len(hits)} pads, expected 1")
            fails.append(f"{ref}.{pin} pad count")
            bad += 1
            continue
        p = hits[0]
        px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        got_net = p.GetNetname()
        got_lbl, dist = min(((t, gap_to(r, px, py)) for t, r in cands),
                            key=lambda v: v[1])
        checked += 1
        if got_lbl != label or dist > MAX_GAP:
            print(f"  [FAIL] {ref}.{pin} printed {got_lbl!r}, want {label!r} "
                  f"(nearest own label {dist:.2f} mm away)")
            fails.append(f"{ref}.{pin} label {got_lbl!r} != {label!r}")
            bad += 1
        if got_net != net:
            print(f"  [FAIL] {ref}.{pin} net {got_net!r}, want {net!r}")
            fails.append(f"{ref}.{pin} net {got_net!r} != {net!r}")
            bad += 1
print(f"  checked {checked} pin(s) for printed label + attached net"
      + ("" if bad else "  -- every label matches its net"))

print("\n== power section: every part inside its own cluster box ==")
print("  (charge and boost are separate clusters on purpose -- each one's power")
print("   loop is only a few mm across, which no autorouter will preserve for you)")
CHARGE_BOX = (63.0, 0.4, 75.0, 11.6)
BOOST_BOX = (75.0, 0.4, 92.0, 14.2)
for name, box, members in (("charge", CHARGE_BOX, ["U1", "C5", "C6", "R2", "R3", "D3"]),
                           ("boost", BOOST_BOX, ["L1", "U2", "D2", "C7", "C8", "R4", "R5"])):
    for ref in members:
        bb = bbox(ref)
        ok = (bb[0] >= box[0] - 0.01 and bb[1] >= box[1] - 0.01
              and bb[2] <= box[2] + 0.01 and bb[3] <= box[3] + 0.01)
        print(f"  [{'OK ' if ok else 'FAIL'}] {ref:<4} in {name} box "
              f"x {bb[0]:6.2f}..{bb[2]:<6.2f} y {bb[1]:5.2f}..{bb[3]:<5.2f}   "
              f"({box[0]:.1f},{box[1]:.1f})-({box[2]:.1f},{box[3]:.1f})")
        if not ok:
            fails.append(f"{ref} outside {name} box")

print("\n== SW_NODE switching loop: U2.SW - L1 - D2(A) pairwise <= 12 mm ==")
print("  (a switching node's loop area is what radiates; the A* router has no")
print("   concept of it, so the guarantee has to come from the placement)")
loop = [("U2.SW", padxy("U2", 1)), ("L1.1", padxy("L1", 1)),
        ("L1.2", padxy("L1", 2)), ("D2.A", padxy("D2", 2))]
for i in range(len(loop)):
    for j in range(i + 1, len(loop)):
        (na, pa), (nb, pb) = loop[i], loop[j]
        d = math.dist(pa, pb)
        ok = d <= 12.0
        print(f"  [{'OK ' if ok else 'FAIL'}] {na:<6} - {nb:<6} {d:6.2f} mm")
        if not ok:
            fails.append(f"SW_NODE loop {na}-{nb} = {d:.1f} mm")

print("\n== power topology: the diode OR and the FB divider ==")
print("  (this is the whole v2 change -- if any one of these is wrong, either the")
print("   battery cannot feed the 5 V rail, or USB and the boost fight each other)")
TOPOLOGY = [
    ("J5", 1, "VBAT"), ("C6", 1, "VBAT"), ("U1", 5, "VBAT"),
    ("C7", 1, "VBAT_SW"), ("L1", 1, "VBAT_SW"), ("U2", 5, "VBAT_SW"),
    # MT3608's EN sits on VBAT_SW, not on +5V: the boost is what *makes* +5V when
    # the battery is alone, so an enable tied to its own output would never come
    # up.  (The plan's net table listed EN under +5V; that is a deadlock.)
    ("U2", 4, "VBAT_SW"),
    ("U2", 1, "SW_NODE"), ("L1", 2, "SW_NODE"), ("D2", 2, "SW_NODE"),
    ("D2", 1, "+5V"),          # cathode to the rail: the OR-ing diode
    ("U2", 3, "FB"), ("R4", 2, "FB"), ("R5", 1, "FB"),
    # The divider samples *after* D2, so the drop across it is inside the loop
    # and the output lands at 4.89 V -- below USB's 5.0 V, which is what makes
    # the diode reverse-bias by itself the moment a charger is plugged in.
    ("R4", 1, "+5V"),
    ("R5", 2, "GND"),
    ("U1", 4, "+5V"), ("U1", 8, "+5V"), ("C5", 1, "+5V"), ("C8", 1, "+5V"),
    ("U1", 2, "PROG"), ("R2", 1, "PROG"), ("R2", 2, "GND"),
    ("U1", 7, "CHRG"), ("D3", 1, "CHRG"), ("D3", 2, "CHG_A"),
    ("R3", 1, "+5V"), ("R3", 2, "CHG_A"),
    # TP4056's TEMP is grounded to disable temperature sensing: the pack has no
    # thermistor, and an open TEMP input makes the charger refuse to start.
    ("U1", 1, "GND"),
]
topo_bad = 0
for ref, pin, want in TOPOLOGY:
    hits = [p for p in fps[ref].Pads() if str(p.GetNumber()) == str(pin)]
    got = hits[0].GetNetname() if len(hits) == 1 else f"<{len(hits)} pads>"
    if got != want:
        print(f"  [FAIL] {ref}.{pin} net {got!r}, want {want!r}")
        fails.append(f"{ref}.{pin} net {got!r} != {want!r}")
        topo_bad += 1
print(f"  checked {len(TOPOLOGY)} power-net pin(s)"
      + ("" if topo_bad else "  -- battery, boost, diode OR and charge path all as designed"))

# The switch gets its own assertion rather than two rows in the table above.
# SW5 is a 3-pad SPDT used as on/off: pin 1 is the common, pin 2 the throw that
# carries the battery, pin 3 the throw left open.  Which of 1/2 lands on VBAT is
# a symbol-convention detail, and a switch is symmetric -- so what actually has
# to hold is that its two live contacts are the battery and the boost input, and
# nothing else.  Stated that way, wiring it to +5V still fails.
sw_nets = {str(p.GetNumber()): p.GetNetname() for p in fps["SW5"].Pads()
           if str(p.GetNumber())}
ok = {sw_nets.get("1"), sw_nets.get("2")} == {"VBAT", "VBAT_SW"} and not sw_nets.get("3")
print(f"  [{'OK ' if ok else 'FAIL'}] SW5 contacts = {sw_nets}  "
      f"(want battery on one, boost input on the other, third open)")
if not ok:
    fails.append(f"SW5 contacts {sw_nets}")

print("\n== no pad left floating except the ones declared unconnected ==")
print("  (the schematic is edited by hand and the board is synced from it, so a")
print("   pin that silently failed to take its label shows up right here)")
# The header table above already declares which header pins are intentionally
# free, so it is the source of truth for those.  The rest are internal to a part:
#   U1.6  TP4056 ~STDBY~: open-drain status output, unused
#   U2.6  MT3608 NC: no internal connection
#   SW5.3 the SPDT's spare throw -- that is what makes the switch an on/off
NC_OK = {(ref, str(pin)) for ref, t in PIN_TABLE.items() for pin, _, net in t if net == ""}
NC_OK |= {("U1", "6"), ("U2", "6"), ("SW5", "3")}
# Pads with no number are the footprint's own mechanical/thermal pads -- SW5's
# two anchor tabs, SOIC-8-1EP's four via rings.  They can never appear in a
# netlist, so "unconnected" is not a statement about them.
floating = sorted({(fp.GetReference(), str(p.GetNumber()))
                   for fp in board.GetFootprints() if not fp.GetReference().startswith("H")
                   for p in fp.Pads() if not p.GetNetname() and str(p.GetNumber())})
stray = [f for f in floating if f not in NC_OK]
print(f"  {len(floating)} pad(s) with no net: {floating}")
if stray:
    print(f"  [FAIL] unexpected unconnected pad(s): {stray}")
    fails.append(f"floating pads {stray}")
else:
    print(f"  [OK ] all {len(floating)} accounted for: the free header pins the")
    print("        table declares, plus U1.6, U2.6 and SW5.3")

print("\n== routing summary ==")
from collections import Counter
nets = Counter(t.GetNetname() for t in board.GetTracks() if t.GetClass() != "PCB_VIA")
vias = Counter(t.GetNetname() for t in board.GetTracks() if t.GetClass() == "PCB_VIA")
nets.pop("", None)
vias.pop("", None)
print(f"  tracks: {sum(nets.values())} over {len(nets)} nets")
print(f"  vias:   {sum(vias.values())}  ({', '.join(f'{k}={v}' for k, v in sorted(vias.items()))})")
widths = {}
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA":
        continue
    widths.setdefault(t.GetNetname(), set()).add(round(pcbnew.ToMM(t.GetWidth()), 3))
# VBAT_SW and SW_NODE are 0.60 rather than the 1.00 the plan called for: U2 is a
# SOT-23-6 whose pads are on 0.95 mm pitch and only 0.60 mm tall, so a 1.00 mm
# trace centred on SW pin 1 needs 0.70 mm of clearance to the neighbouring pad's
# copper edge, which is 0.65 mm away -- impossible, not merely tight.  0.60 mm of
# 1 oz copper is still good for ~1.5 A, and the runs are a few mm long.
for want, w in (("+5V", 1.00), ("VBAT", 1.00), ("+3V3", 0.80),
                ("VBAT_SW", 0.60), ("SW_NODE", 0.60), ("I2S_BCK", 0.30)):
    ws = sorted(widths.get(want, []))
    ok = bool(ws) and ws[0] >= w - 0.001
    print(f"  [{'OK ' if ok else 'FAIL'}] {want:<9} width(s) {ws}  (want >= {w})")
    if not ok:
        fails.append(f"{want} too thin")
zoned = [z for z in board.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()]
rule = [z for z in board.Zones() if z.GetIsRuleArea()]
gnd_tracks = nets.get("GND", 0) + vias.get("GND", 0)
print(f"  GND: {len(zoned)} pour zone(s), {vias.get('GND', 0)} stitching via(s), "
      f"{gnd_tracks} GND track/via total (routing GND is not expected)")
print(f"  rule areas: {len(rule)} (expect 4, one per screw hole)")

print("\n" + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILURE(S): {fails}"))
