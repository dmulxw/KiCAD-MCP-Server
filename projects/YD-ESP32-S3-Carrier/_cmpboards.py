"""Is it safe to graft the old routing onto the new board?

The plan is to keep the committed board's copper (it is fully routed) and route
only the 34 nets the 74HC595 change added, instead of re-routing 74 nets from
scratch and losing.  That is only legitimate if every pad the old copper touches
is still in exactly the same place -- a fraction of a millimetre would turn the
graft into a forest of near-miss connections that DRC reports as unconnected.

So: compare, per pre-existing reference, the full (pad, x, y, net) set between
the committed board and the working one.  Anything that moved is disqualifying.
"""
import sys

import pcbnew

S = 1e6
HEAD = "_base_test.kicad_pcb"
WORK = "YD-ESP32-S3-Carrier.kicad_pcb"

# The 14 parts this change added -- they have no counterpart in the old board,
# and their absence from it is not a mismatch.
NEW = {"U3", "U4", "U5", "U6", "J8", "J10",
       "C9", "C10", "C11", "C12", "R6", "R7", "R8", "R9"}


def snapshot(path):
    board = pcbnew.LoadBoard(path)
    fps = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pads = []
        for p in fp.Pads():
            pos = p.GetPosition()
            pads.append((p.GetPadName(), round(pos.x / S, 4), round(pos.y / S, 4),
                         p.GetNetname()))
        fps[ref] = sorted(pads)
    tracks = list(board.GetTracks())
    n_via = sum(1 for t in tracks if t.GetClass() == "PCB_VIA")
    e = board.GetBoardEdgesBoundingBox()
    info = {
        "fps": fps,
        "tracks": len(tracks) - n_via,
        "vias": n_via,
        "outline": (e.GetLeft() / S, e.GetTop() / S, e.GetRight() / S, e.GetBottom() / S),
    }
    return board, info


# Both boards live in this process at once.  No Remove() is called anywhere, so
# the SWIG graveyard hazard that bites clear_routing() does not apply here.
head_board, head = snapshot(HEAD)
work_board, work = snapshot(WORK)

print("outline  head x %.2f..%.2f y %.2f..%.2f" % head["outline"])
print("outline  work x %.2f..%.2f y %.2f..%.2f" % work["outline"])
print("copper   head %d tracks %d vias" % (head["tracks"], head["vias"]))
print("copper   work %d tracks %d vias" % (work["tracks"], work["vias"]))
print("parts    head %d   work %d" % (len(head["fps"]), len(work["fps"])))

added = sorted(set(work["fps"]) - set(head["fps"]))
removed = sorted(set(head["fps"]) - set(work["fps"]))
print("\nadded in work  : %s" % (", ".join(added) if added else "(none)"))
print("gone from work : %s" % (", ".join(removed) if removed else "(none)"))

bad = []
for ref in sorted(set(head["fps"]) & set(work["fps"])):
    h, w = head["fps"][ref], work["fps"][ref]
    if h == w:
        continue
    hp = {p[0]: p[1:] for p in h}
    wp = {p[0]: p[1:] for p in w}
    for name in sorted(set(hp) | set(wp)):
        if hp.get(name) != wp.get(name):
            bad.append("%s pad %s: %s -> %s" % (ref, name, hp.get(name), wp.get(name)))

print()
if bad:
    print("*** pre-existing pads MOVED -- grafting is NOT safe ***")
    for b in bad[:60]:
        print("   " + b)
    print("   ... %d total" % len(bad))
    sys.exit(1)

print("all %d pre-existing parts pad-for-pad identical -- grafting is safe"
      % len(set(head["fps"]) & set(work["fps"])))
