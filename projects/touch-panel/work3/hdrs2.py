"""Add the two 1x20 headers to the INTACT baseline, as a parallel breakout port.

This is the "keep the FPC" branch.  _fh0 was built from _nofpc0 -- the FPC
footprint removed and its 38 netted pads replaced by centreline copper -- which
is the right base if the headers are meant to REPLACE the FPC.  They are not,
this time: the user kept the FPC and wants the headers alongside it.

So start from touch-panel.kicad_pcb itself, the one board in this project that
is known good (53 violations / 2 unconnected, md5-identical to the copy one
directory up), and only ADD:

  * J1A at (95.4, 115.67) and J1B at (175.6, 180.97)
  * the widen() that makes room for them (x 90..181)

Nothing is removed and nothing is re-netted yet, so the DRC of the result must
read exactly what the baseline reads -- 53 / 2 -- except for the 40 newly-netted
header pins, which arrive as 40 unconnected items because they have no copper
yet.  104 / 42 would be the honest reading of this intermediate state.

The stale-copper cleanup in hdrs.py is deliberately NOT carried over.  It exists
there because _final already had ROW3/ROW5 tracks landing on J1A pads whose nets
the new assignment re-purposed.  On the untouched baseline there is no J1A at
all, and every track near a header pad is legitimate fanout copper that the
touches() predicate would happily delete.

    python hdrs2.py [src] [out]
"""
import collections
import os
import sys

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402
import edgeflood as E                                                # noqa: E402

S = 1e6
SRC = sys.argv[1] if len(sys.argv) > 1 else "touch-panel.kicad_pcb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "_par0.kicad_pcb"

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
print("%s: %d footprint(s), %d track(s), J1=%s J1A=%s J1B=%s"
      % (SRC, len(have), len(list(board.GetTracks())),
         "yes" if "J1" in have else "NO",
         "yes" if "J1A" in have else "no", "yes" if "J1B" in have else "no"))

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
        where = ("already in place" if abs(cur.x / S - at[0]) <= 0.01
                 and abs(cur.y / S - at[1]) <= 0.01
                 else "moved from (%.2f, %.2f)" % (cur.x / S, cur.y / S))
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
# routing on the un-widened board died with "ROW5 ... expanded 0" followed by an
# out-of-bounds goal index (761 into an axis of 722).  That is not a routing
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
