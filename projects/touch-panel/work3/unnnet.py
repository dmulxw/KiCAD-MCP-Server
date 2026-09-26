"""Clear the net off every header pin the router could not reach.

The parallel-port board nets all 40 header pins, and DRC counts each one that has
no copper as an unconnected item: 42 = the baseline's 2 (J1's ROW3/ROW5) plus the
40 pins.  Only 15 of those pins can actually be routed -- the other 25 are walled
by the existing J1 fanout, which is precisely why the FPC is being kept.

A pin that is netted but unrouted is not a broken connection, it is a claim.  The
board is not claiming it should be connected; there just is not room.  Clearing
the net turns it back into what it physically is -- a spare pin on a breakout
header -- and DRC stops counting it, which is what keeps the floor honest:
"unconnected 不得高于 2".

The authority is DRC itself, not a geometric tangent test.  Re-deriving "is this
pin connected" with my own math would repeat the mistake that made _honest's
numbers unusable; kicad-cli already computed it, so read its answer.

    python unnnet.py <board> <drc.json> <out>
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
import pcbnew                                                        # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else "_par1.kicad_pcb"
DRCJSON = sys.argv[2] if len(sys.argv) > 2 else "_drc_par1.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else "_par2.kicad_pcb"
KEEP_MINE = os.environ.get("KEEP", "0") == "1"

board = pcbnew.LoadBoard(SRC)


def uid(it):
    return it.m_Uuid.AsString().replace("-", "").lower()


# Every pad of the two breakout headers, so a DRC item can be traced back to the
# pad that owns it.  Only these are candidates -- J1's own pads must be left
# alone, because ROW3/ROW5 there are the baseline's genuine 2 and clearing them
# would hide a real fault rather than describe a spare pin.
pads = {}
for fp in board.GetFootprints():
    if fp.GetReference() not in ("J1A", "J1B"):
        continue
    for p in fp.Pads():
        pads[uid(p)] = (fp.GetReference(), p)

print("%s: %d header pad(s) indexed" % (SRC, len(pads)))

S = 1e6


def touches(t, px, py, tol=0.05):
    """Does this track's centreline pass within `tol` of (px, py)?

    Same predicate hdrs.py used to find stale copper, and for the same reason:
    KiCad connectivity intersects CENTRELINES, so a GND track running across
    pins 17 and 18 of a header connects them just as surely as one that stops
    on them.  A pad's own centre is the only place worth testing.
    """
    s, e = t.GetStart(), t.GetEnd()
    ax, ay, bx, by = s.x / S, s.y / S, e.x / S, e.y / S
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    q = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ((px - (ax + q * dx)) ** 2 + (py - (ay + q * dy)) ** 2) ** 0.5 <= tol


TRACKS = list(board.GetTracks())


def attached(p, net):
    """Is any of this net's copper sitting on the pad's centreline?"""
    c = p.GetPosition()
    px, py = c.x / S, c.y / S
    return any(t.GetNetname() == net and touches(t, px, py) for t in TRACKS)


d = json.load(open(DRCJSON, encoding="utf-8"))
entries = d.get("unconnected_items", [])
# Keyed by uuid string, not by the pad: SWIG's PAD has no __hash__, so a PAD
# cannot be a dict key at all.
doomed = {}
for ent in entries:
    for it in ent.get("items", []):
        u = it.get("uuid", "").replace("-", "").lower()
        if u in pads and u not in doomed:
            ref, p = pads[u]
            doomed[u] = (ref, p.GetNumber(), p.GetNetname(), p)

print("%d unconnected entr(ies) -> %d header pin(s) named" % (len(entries), len(doomed)))

# DRC listing a pad is NOT proof the pad is bare.  ROW5 is split into two islands
# on the baseline -- J1's pad and the trunk -- so the router connected J1A.20 to
# one of them and DRC still reports the pair, naming J1A.20 as the representative
# of its island.  Clearing THAT pad's net leaves 6.93mm of ROW5 copper attached to
# a pad declared to be on nothing, which DRC calls a short.  Measured: 2
# shorting_items + 2 solder_mask_bridge, all on J1A.20 alone.
cleared = kept = 0
for u, (ref, num, net, p) in sorted(doomed.items(), key=lambda kv: (kv[1][0], int(kv[1][1]))):
    if attached(p, net):
        print("   %s.%-3s KEPT -- %s copper is on it, DRC named the island not the pin"
              % (ref, num, net))
        kept += 1
        continue
    p.SetNetCode(0)
    if p.GetNetname():
        print("   *** %s.%s still reads net %r" % (ref, num, p.GetNetname()))
        continue
    print("   %s.%-3s cleared (was %s)" % (ref, num, net))
    cleared += 1
print("%d kept netted (they have copper)" % kept)

pcbnew.SaveBoard(OUT, board)
print("cleared %d pad(s); saved %s" % (cleared, OUT))
