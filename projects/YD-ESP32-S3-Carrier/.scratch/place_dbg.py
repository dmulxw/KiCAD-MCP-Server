"""Put every footprint where the mechanical drawing says it goes, then draw the board.

Anchoring on pad 1 rather than the footprint origin means the coordinates below are
the ones you can actually measure with calipers against the plugged-in modules.  The
placer brute-forces the rotation: it sets the part to (0,0)/0deg, snapshots where
pad 2 sits relative to pad 1, then tries 0/90/180/270 until pad 2 points the way the
sheet asks for.  That saves writing four sets of cos/sin by hand for every symbol.

Idempotent -- re-running moves everything back to the same place and redraws the
board outline from scratch.

Run:
  "C:/Program Files/KiCad/10.0/bin/python.exe" scripts/place.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")

BOARD_W, BOARD_H = 100.0, 64.0

FPLIB = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"

# Update-PCB-from-Schematic adds footprints that are missing but never swaps the
# library link of one that is already on the board, so the Ø3.2 hole has to be
# replaced by hand.  (value, library, footprint) keyed by reference.
SWAP = {
    "H1": ("MountingHole", "MountingHole_3.2mm_M3"),
    "H2": ("MountingHole", "MountingHole_3.2mm_M3"),
    "H3": ("MountingHole", "MountingHole_3.2mm_M3"),
    "H4": ("MountingHole", "MountingHole_3.2mm_M3"),
}

# (reference, pad name, board position of that pad in mm, direction pad2 lies in)
#
# The v2 board is 24 mm shorter and 26 mm wider: the bottom edge now sits on the dev
# board's USB edge (y 63.25) so the socket hangs off the board instead of being
# buried behind it, and the extra width is what the power section and the three
# spare-IO headers live in.
PLACE = [
    # --- dev board + audio module + display + battery (hard mechanical anchors) ---
    ("J1",  "pad1", (11.00,  8.00), "down"),
    ("J2",  "pad1", (36.40,  8.00), "down"),
    ("J3",  "pad1", (46.00, 32.00), "right"),
    ("J4",  "pad1", (82.00, 31.00), "down"),
    ("J5",  "pad1", (43.60,  5.40), "right"),

    # --- power switch + the four buttons -----------------------------------------
    ("SW5", "pad1", (55.00,  7.00), "right"),
    ("SW1", "pad1", (44.50, 59.00), "right"),
    ("SW2", "pad1", (55.50, 59.00), "right"),
    ("SW3", "pad1", (66.50, 59.00), "right"),
    ("SW4", "pad1", (77.50, 59.00), "right"),

    # --- spare IO + UART1 ---------------------------------------------------------
    # J6 sits at y 17.5 rather than up against the power section: the 4 mm band
    # directly under U2 is what the FB divider needs, and FB is a high-impedance
    # node that wants the shortest possible trace.  J7 then stacks 8.5 mm below it,
    # still 1.4 mm clear of J4's courtyard top.
    ("J6",  "pad1", (76.50, 17.50), "right"),
    ("J7",  "pad1", (76.50, 26.00), "right"),
    ("J9",  "pad1", (90.00, 42.00), "right"),

    # --- filtering / indicator row (C1 C2 C3 C4 D1 R1), below J3's labels --------
    # R1 is a vertical axial part 9.77 mm tall, so the row is anchored on a common
    # top edge (y 36.5) rather than a common pad row; its bbox bottom lands at
    # 46.27, still 4.7 mm clear of the buttons.
    ("C1",  "pad1", (45.275, 38.115), "down"),
    ("C2",  "pad1", (50.075, 37.575), "down"),
    ("C3",  "pad1", (54.875, 38.115), "down"),
    ("C4",  "pad1", (59.675, 37.575), "down"),
    ("D1",  "pad1", (64.935, 38.465), "down"),
    ("R1",  "pad1", (70.195, 37.575), "down"),

    # --- charge cluster (x 63.5-74.7, y 0.8-11.2) --------------------------------
    # Row 1 (y 0.8-2.79): R2 PROG->GND, R3 +5V->CHG_A, D3 CHRG->CHG_A.
    #   R3's pad 2 and D3's pad 2 are the CHG_A pair, so they face each other across
    #   the 0.4 mm gap between the two courtyards.
    # Row 2 (y 3.1-8.59): U1.  Pads 1-4 down the left (TEMP PROG GND VCC), 5-8 up the
    #   right (BAT STDBY CHRG CE) -- so VCC ends up bottom-left, next to C5, and BAT
    #   bottom-right, next to C6.
    # Row 3 (y 8.8-11.19): C5 on +5V, C6 on VBAT.
    ("R2",  "pad1", (66.1375, 1.795), "left"),
    ("R3",  "pad1", (68.1625, 1.795), "right"),
    ("D3",  "pad1", (73.8625, 1.795), "left"),
    ("U1",  "pad1", (64.7700, 3.940), "down"),
    ("C5",  "pad1", (67.3200, 9.995), "left"),
    ("C6",  "pad1", (72.3200, 9.995), "left"),

    # --- boost cluster (x 75.2-91.7, y 0.8-13.8) ---------------------------------
    # The SW_NODE loop is the one that matters: L1 (pad 2) - D2 (pad 2, anode) -
    # U2.SW are 2.6 / 3.5 / 3.6 mm apart, all inside the 12 mm the verifier allows.
    # The FB divider sits directly under U2.FB on purpose -- FB is a high-impedance
    # node and the trace to it is the shortest one on the board, so it drops 2.7 mm
    # straight down from U2.FB (83.3575, 10.695) into the gap J6 leaves at y 11.8.
    ("C7",  "pad1", (79.0200,  1.995), "left"),
    ("L1",  "pad1", (76.3450,  7.595), "right"),
    ("D2",  "pad1", (87.9450,  5.295), "left"),
    ("U2",  "pad1", (83.3575,  8.795), "down"),
    ("C8",  "pad1", (90.8200, 10.095), "left"),
    ("R4",  "pad1", (83.2125, 12.795), "right"),
    ("R5",  "pad1", (86.9625, 12.795), "right"),

    # --- M3 clearance holes, inset 4.5 mm ----------------------------------------
    # 3.2 mm, not 3.0: a standard M3 screw wants a 3.2 mm clearance hole.
    ("H1",  "origin", (4.5,  4.5), None),
    ("H2",  "origin", (95.5,  4.5), None),
    ("H3",  "origin", (4.5, 59.5), None),
    ("H4",  "origin", (95.5, 59.5), None),
]

DIRS = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def mm(v):
    return pcbnew.ToMM(v)


def anchor_pad(fp, number):
    """The named pad, or None.

    It has to be looked up by number rather than guessed at: SOIC-8-1EP puts its
    thermal pad dead on the footprint origin, so 'the pad nearest the origin' is
    pad 9 there, not pad 1.
    """
    for p in fp.Pads():
        if str(p.GetNumber()) == number:
            return p
    return None


def pad2_of(fp, first):
    """The nearest other pad to `first` -- pad 2 on every two-pad part, and for the
    multi-pad ones it is the neighbour that defines which way the part faces."""
    best, bestd = None, None
    for p in fp.Pads():
        if p.GetNumber() == first.GetNumber():
            continue
        d = (p.GetPosition() - first.GetPosition()).EuclideanNorm()
        if bestd is None or d < bestd:
            best, bestd = p, d
    return best


# Library footprints carried over from an older board can hold drills the fab
# will not make.  U1's SOIC-8-1EP with thermal vias is the one that does:
# KiCad's own EP2.41x3.3mm_ThermalVias footprint drills its six thermal vias at
# Ø0.20, and this board's design rules floor holes at Ø0.30.
#
# The choice is to raise the floor to 0.20 or to widen the vias.  Widening wins:
# 0.30 is a size every fab lists, so the board does not depend on a house
# offering the smallest drill it can -- and loosening a board-wide rule to admit
# one library part is the wrong direction anyway.  The vias stay inside the
# exposed pad, so the thermal path is unchanged.
MIN_DRILL = 0.30
DRILL_FIX = {"U1": (0.30, 0.60)}   # ref -> (drill, pad size); pad grows with it


def fix_thermal_vias(by_ref):
    """Widen any PTH drill below MIN_DRILL, growing the pad to keep the annulus.

    A Ø0.20 drill under a Ø0.50 pad is fine until the drill becomes Ø0.30, at
    which point the ring is down to 0.10 mm -- under JLCPCB's 0.13 mm minimum.
    So the pad is set alongside the drill rather than left alone.

    Takes the reference map main() already built rather than looking anything up
    again -- see footprint_map() for why a second lookup pass is the thing that
    breaks the board.
    """
    for ref, (drill, size) in DRILL_FIX.items():
        fp = by_ref.get(ref)
        if fp is None:
            print(f"  {ref}: not on the board, skipping the drill fix")
            continue
        changed = 0
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                continue
            if mm(p.GetDrillSize().x) >= MIN_DRILL:
                continue
            p.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(drill), pcbnew.FromMM(drill)))
            p.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
            changed += 1
        if changed:
            print(f"  {ref}: {changed} thermal via(s) widened to Ø{drill} drill / "
                  f"Ø{size} pad, annulus {(size - drill) / 2:.2f} mm")


def footprint_map(board):
    """Every footprint keyed by reference, in one dict held for the whole run.

    board.FindFootprintByReference() reads as the natural way to do this, but it
    is not safe to call in a loop.  Each call hands back a *fresh* proxy for a
    pointer the board already owns; once those proxies are collected the board's
    own footprint list is left holding freed entries.  Nothing goes wrong at the
    call that did it -- the damage surfaces later, on the next walk of
    board.GetFootprints(), as an access violation inside SWIG:

        File "pcbnew.py", line 21838 in Footprints
        File "pcbnew.py", line 22614 in GetFootprints

    and, short of a crash, as FindFootprintByReference returning a bare
    SwigPyObject that answers no attributes ("'SwigPyObject' object has no
    attribute 'Pads'").  Building the map once and keeping it alive sidesteps the
    churn, and matching on the reference string makes it independent of the order
    KiCad happens to keep the footprints in.
    """
    return {str(f.GetReference()): f for f in board.GetFootprints()}


def main():
    board = pcbnew.LoadBoard(BOARD)
    by_ref = footprint_map(board)
    _probe("after footprint_map", by_ref)

    missing = [ref for ref, _, _, _ in PLACE if ref not in by_ref]
    if missing:
        raise SystemExit(
            f"not on the board yet: {', '.join(missing)}\n"
            "run sync_schematic_to_board first -- placement needs the footprints present")

    # Swap any footprint whose library link is stale.  These are plain NPTH pads
    # with no net, so the replacement carries no connectivity over.
    retired = []
    for ref, (lib, name) in SWAP.items():
        fp = by_ref.get(ref)
        if fp is not None and str(fp.GetFPID().GetLibItemName()) == name:
            continue
        new = pcbnew.FootprintLoad(f"{FPLIB}\\{lib}.pretty", name)
        if new is None:
            raise SystemExit(f"can't load {lib}:{name}")
        new.SetReference(ref)
        new.SetValue(name)
        if fp is not None:
            board.Remove(fp)
            retired.append(fp)   # hold the proxy: freeing it while board is live breaks SWIG
        board.Add(new)
        by_ref[ref] = new
        print(f"  swapped {ref} -> {lib}:{name}")

    _probe("before PLACE loop", by_ref)

    for ref, padname, (tx, ty), direction in PLACE:
        fp = by_ref[ref]

        # Park it, so the rotation search starts from a known pose -- footprint
        # positions are absolute and SetPosition would otherwise be a no-op delta.
        fp.SetOrientationDegrees(0)
        fp.SetPosition(vec(0, 0))

        if padname == "origin":
            fp.SetPosition(vec(tx, ty))
            continue

        number = padname[3:] if padname.startswith("pad") else padname
        want = DIRS[direction]

        for angle in (0, 90, 180, 270):
            fp.SetOrientationDegrees(angle)
            # Re-read the pads: SetOrientation rewrites their absolute positions.
            first = anchor_pad(fp, number)
            if first is None:
                raise SystemExit(f"{ref}: no pad {number}")
            p2 = pad2_of(fp, first)
            d = p2.GetPosition() - first.GetPosition()
            dx, dy = mm(d.x), mm(d.y)
            if dx * want[0] + dy * want[1] > 0 and abs(dx * want[1] - dy * want[0]) < 0.02:
                break
        else:
            raise SystemExit(f"{ref}: no rotation puts pad 2 {direction}")

        delta = vec(tx, ty) - first.GetPosition()
        fp.SetPosition(fp.GetPosition() + delta)

    _probe("after PLACE loop", by_ref)

    # Board outline: drop whatever is there and draw the v2 rectangle.
    for d in list(board.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            board.Remove(d)
    for (x0, y0), (x1, y1) in (((0, 0), (BOARD_W, 0)),
                               ((BOARD_W, 0), (BOARD_W, BOARD_H)),
                               ((BOARD_W, BOARD_H), (0, BOARD_H)),
                               ((0, BOARD_H), (0, 0))):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.10))
        seg.SetStart(vec(x0, y0))
        seg.SetEnd(vec(x1, y1))
        board.Add(seg)

    _probe("after outline rebuild", by_ref)
    fix_thermal_vias(by_ref)

    board.Save(BOARD)
    print(f"placed {len(PLACE)} footprints, outline "
          f"{BOARD_W:.1f} x {BOARD_H:.1f} mm -> {BOARD}")



def _probe(tag, by_ref):
    fp = by_ref.get("U1")
    try:
        n = len(list(fp.Pads()))
        print(f"  PROBE {tag:<26} U1 {type(fp).__name__} Pads->{n}", flush=True)
    except Exception as e:
        print(f"  PROBE {tag:<26} U1 {type(fp).__name__} RAISED {type(e).__name__}: {e}", flush=True)

main()
