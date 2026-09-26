"""Put both 1x20 headers on the junction-preserving no-FPC board and net them.

_pins.kicad_pcb netted the headers on _rip3 -- a board already missing 77
connections, which is why route40's 40 pin routes could not be judged on their
own: every DRC number it produced carried the rip damage with it.

_nofpc.kicad_pcb is the clean base.  The FPC footprint is gone, its 38 netted
pads replaced by centreline copper, and DRC reads 0 unconnected -- the rip never
happened.  Netting the headers here means the only thing left to fail is the 40
pin routes themselves, one unconnected item per unrouted pin.

Assignment is pins.py's, which was read off reach2/reach3 and differs from the
plan's a-priori table on purpose (the plan sent ROW10 165mm around the board;
the measurement found it 5.6mm from J1B).  ROW3 and ROW5 keep the user's
requirement of sitting at the two ends of the same connector.

    python hdrs.py [src] [out]
"""
import collections
import os
import sys

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402
import edgeflood as E                                                # noqa: E402

S = 1e6
SRC = sys.argv[1] if len(sys.argv) > 1 else "_nofpc.kicad_pcb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "_fh.kicad_pcb"

J1A_AT = (95.4, 115.67)
J1B_AT = (175.6, 180.97)

J1A = {1: "ROW3", 2: "ROW0", 3: "ROW1", 4: "ROW2", 5: "ROW4", 6: "ROW6",
       7: "ROW7", 8: "ROW8", 9: "ROW9", 10: "ROW13", 11: "ROW14",
       12: "ROW16", 13: "ROW17", 14: "CSEL4", 15: "CSEL3",
       16: "GND", 17: "GND", 18: "GND", 19: "GND", 20: "ROW5"}
J1B = {1: "ROW10", 2: "ROW11", 3: "ROW12", 4: "ROW15", 5: "ROW18",
       6: "ROW19", 7: "ROW20", 8: "CSEL0", 9: "CSEL1", 10: "CSEL2",
       11: "CSEL5", 12: "CSEL6", 13: "CSEL7", 14: "CSEL8", 15: "CSEL9",
       16: "GND", 17: "+3V3", 18: "+3V3", 19: "+3V3", 20: "+3V3"}
TABLE = {"J1A": J1A, "J1B": J1B}

want = collections.Counter(list(J1A.values()) + list(J1B.values()))
print("assignment: %d pin(s)" % sum(want.values()))
for pref, n in (("ROW", 21), ("CSEL", 10), ("GND", 5), ("+3V3", 4)):
    got = sum(c for k, c in want.items() if k.startswith(pref))
    print("   %-6s %2d (need %d) %s" % (pref, got, n, "ok" if got == n else "*** MISMATCH ***"))

board = pcbnew.LoadBoard(SRC)
have = {fp.GetReference(): fp for fp in board.GetFootprints()}
print("%s: %d footprint(s), J1A=%s" % (SRC, len(have), "yes" if "J1A" in have else "NO"))

FPNAME = "PinHeader_1x20_P2.54mm_Vertical"
FPLIB = "C:/Program Files/KiCad/10.0/share/kicad/footprints/Connector_PinHeader_2.54mm.pretty"


def load_header(ref, at):
    """Add one 1x20 header at `at` mm, or put the existing one there.

    FootprintLoad hands the part back at the origin, so the placement is not
    optional: a header left at (0,0) sits 95mm off the board edge with all 40
    pads stacked on a single point, and every net on it reads as unrouted for
    a reason that has nothing to do with routing.
    """
    fp = have.get(ref)
    if fp is None:
        fp = pcbnew.FootprintLoad(FPLIB, FPNAME)
        if fp is None:
            print("*** FootprintLoad failed for %s" % FPNAME)
            sys.exit(1)
        fp.SetReference(ref)
        board.Add(fp)
        have[ref] = fp
        where = "added"
    else:
        cur = fp.GetPosition()
        if abs(cur.x / S - at[0]) > 0.01 or abs(cur.y / S - at[1]) > 0.01:
            where = "moved from (%.2f, %.2f)" % (cur.x / S, cur.y / S)
        else:
            where = "already in place"
    fp.SetPosition(pcbnew.VECTOR2I(int(round(at[0] * S)), int(round(at[1] * S))))
    print("%s: %s at %s" % (ref, where, at))
    return fp


for ref, at in (("J1A", J1A_AT), ("J1B", J1B_AT)):
    fp = load_header(ref, at)
    c = fp.GetPosition()
    print("%s at (%.2f, %.2f)  pad span y %.2f..%.2f"
          % (ref, c.x / S, c.y / S, c.y / S, c.y / S + 19 * 2.54))

# The headers only fit if the board grows.  At x 95.4 / 175.6 their pads sit
# 4.6mm outside the original 100..171 outline, and NGrid is built from
# GetBoardEdgesBoundingBox() -- so an off-board pad has no cell at all, and
# route40 on the un-widened board died with "ROW5 ... expanded 0" followed by
# an out-of-bounds goal index (761 into an axis of 722).  That is not a routing
# failure, it is the outline still being the old one.
before = board.GetBoardEdgesBoundingBox()
moved = E.widen(board)
after = board.GetBoardEdgesBoundingBox()
print("outline x %.3f..%.3f -> %.3f..%.3f  y %.3f..%.3f  (%d segment(s) remapped)"
      % (before.GetLeft() / S, before.GetRight() / S,
         after.GetLeft() / S, after.GetRight() / S,
         after.GetTop() / S, after.GetBottom() / S, moved))
if after.GetLeft() / S > J1A_AT[0] or after.GetRight() / S < J1B_AT[0]:
    print("*** outline still does not contain both headers")
    sys.exit(1)

# J1A arrives from _final already carrying two routes: ROW3 landed on pad 5 and
# ROW5 on pad 10, because _final was built before the assignment settled.  This
# script re-purposes pad 5 to ROW4 and pad 10 to ROW13, so those two tracks now
# end on a pad of the wrong net -- measured as exactly 4 shorting_items
# (ROW3<->ROW4 twice, ROW5<->ROW13 twice) plus 4 solder_mask_bridge.
#
# Clear them off before re-netting.  ROW3/ROW5 go back to 2 unconnected for the
# moment, which is correct: route40.py re-routes both to the pins the assignment
# actually gives them (J1A.1 and J1A.20), and it does so first.
_GRAVE = []


def touches(t, px, py, tol=0.05):
    """Does this track's centreline pass within `tol` of (px, py)?

    Endpoint matching is not enough: KiCad connectivity intersects centrelines,
    so a route that passes through a pad without terminating on it is just as
    shorted as one that ends there.
    """
    s, e = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = s.x / S, s.y / S, e.x / S, e.y / S
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    q = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - (ax + q * dx)) ** 2 + (py - (ay + q * dy)) ** 2) ** 0.5 <= tol


cleared = 0
for ref, table in TABLE.items():
    f = have[ref]
    for p in f.Pads():
        try:
            num = int(p.GetNumber())
        except ValueError:
            continue
        want_net = table.get(num)
        if not want_net:
            continue
        c = p.GetPosition()
        px, py = c.x / S, c.y / S
        for t in list(board.GetTracks()):
            if t.GetNetname() == want_net:
                continue
            if touches(t, px, py):
                board.Remove(t)
                _GRAVE.append(t)
                cleared += 1
print("cleared %d stale item(s) off re-purposed pad(s)" % cleared)

missing = set()
for ref, table in TABLE.items():
    f = have[ref]
    done = 0
    for p in f.Pads():
        try:
            num = int(p.GetNumber())
        except ValueError:
            continue
        name = table.get(num)
        if not name:
            continue
        net = board.FindNet(name)
        if net is None:
            missing.add(name)
            continue
        p.SetNet(net)
        done += 1
    print("%s: %d pad(s) netted" % (ref, done))

if missing:
    print("*** nets not found on the board: %s" % sorted(missing))

pcbnew.SaveBoard(OUT, board)
print("saved %s" % OUT)
