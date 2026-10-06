"""One-off: put the committed routing back on the panel-driver board.

The from-scratch route.py run stranded 20 nets and, per its own final step,
stripped their partial copper -- leaving the board with 1271 tracks that are
worse than useless.  route.py's incremental mode freezes whatever copper it
finds on the board, so the board has to be holding the good routing before that
runs.  This copies the committed revision's copper across, replacing everything.

The new footprints and the 74 mm outline are NOT touched: only tracks and vias
move.  _cmpboards.py already proved every pre-existing pad is in the same place
on both boards, so the old copper lands on the same pads it was routed to.

board.Remove() is used, so the removed proxies are held in a module-level list --
see the note on clear_routing() in route.py for what happens to SWIG's type table
if Python frees them while the board is live.
"""
import sys

import pcbnew

WORK = "YD-ESP32-S3-Carrier.kicad_pcb"
GOOD = "_good.kicad_pcb"

_GRAVEYARD = []

work = pcbnew.LoadBoard(WORK)
good = pcbnew.LoadBoard(GOOD)

# Net codes are per-board, so resolve every net by name against the destination.
nets = {}
for name, ni in work.GetNetsByName().items():
    nets[str(name)] = ni.GetNetCode()

removed = 0
for t in list(work.GetTracks()):
    parent = t.GetParent()
    if parent is not None and parent.GetClass() == "FOOTPRINT":
        continue                    # U1's thermal vias are the footprint's
    work.Remove(t)
    _GRAVEYARD.append(t)
    removed += 1

added = skipped = 0
for t in good.GetTracks():
    parent = t.GetParent()
    if parent is not None and parent.GetClass() == "FOOTPRINT":
        continue
    net = t.GetNetname()
    code = nets.get(net)
    if code is None:
        skipped += 1
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1 = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
    x2, y2 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)

    if t.GetClass() == "PCB_VIA":
        v = pcbnew.PCB_VIA(work)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        v.SetWidth(t.GetWidth())
        v.SetDrill(t.GetDrillValue())
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNetCode(code)
        work.Add(v)
        added += 1
        continue

    if t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
        skipped += 1
        continue
    nt = pcbnew.PCB_TRACK(work)
    nt.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    nt.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    nt.SetWidth(t.GetWidth())
    nt.SetLayer(t.GetLayer())
    nt.SetNetCode(code)
    work.Add(nt)
    added += 1

work.Save(WORK)

kept = [t for t in work.GetTracks()
        if t.GetParent() is not None and t.GetParent().GetClass() == "FOOTPRINT"]
print("removed %d item(s) of partial copper" % removed)
print("restored %d item(s) from %s (%d skipped)" % (added, GOOD, skipped))
print("board now holds %d item(s), %d of them footprint-owned"
      % (len(list(work.GetTracks())), len(kept)))
print("saved", WORK)
sys.exit(0 if skipped == 0 else 1)
