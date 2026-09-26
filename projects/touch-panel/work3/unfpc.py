"""Remove the FPC footprint without losing the junctions it was holding.

WHY
---
_rip3/_r2/_r3/_t2 all attack the fanout by *deleting copper* and then trying to
re-bridge what falls apart.  That is treating a symptom.  The control run says
where the damage really comes from: `_drc_j1gone.json` is _final with ONLY the
`J1` footprint removed -- not one track touched -- and it reads

    base  _drc_base_now.json   53 viol /   2 unconnected
    J1 gone  _drc_j1gone.json 161 viol /  64 unconnected   (track_dangling 0->105)

so the pads were not endpoints, they were JOINTS.  A `Conn_01x40` FPC pad in
this fanout is where two or more branches of one net meet; KiCad's connectivity
intersects centrelines at the pad, so removing it severs every branch that met
there.  64 unconnected from 40 pads (38 netted) is that, and nothing else.

So keep the copper and drop the component.  Each pad is replaced by a track
segment along the pad's own centreline, at the pad's width and length, on the
pad's net.  Anything that attached to the pad attaches to the segment, because
the segment occupies the same centreline the pad did -- and the footprint, which
is what the user asked to be rid of, is gone.

    python unfpc.py                     # _final -> _nofpc
    python unfpc.py <src> <out>
"""
import sys, os
sys.path.insert(0, os.getcwd())
import pcbnew

S = 1e6
SRC = sys.argv[1] if len(sys.argv) > 1 else "_final.kicad_pcb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "_nofpc.kicad_pcb"
REF = os.environ.get("REF", "J1")

board = pcbnew.LoadBoard(SRC)

fps = [f for f in board.GetFootprints() if f.GetReference() == REF]
if not fps:
    print("no footprint %s on %s" % (REF, SRC))
    sys.exit(1)
fp = fps[0]

# Snapshot before touching the board: after Remove() the pads are gone.
PADS = []
for p in fp.Pads():
    c = p.GetPosition()
    sz = p.GetSize()
    lay = [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)] or [pcbnew.F_Cu]
    PADS.append((p.GetNumber(), c.x / S, c.y / S, sz.x / S, sz.y / S,
                 lay[0], p.GetNetname()))

print("%s: %s %s -- %d pad(s), %d netted"
      % (SRC, REF, fp.GetFPID().GetLibItemName(), len(PADS),
         sum(1 for q in PADS if q[6])), flush=True)

board.Remove(fp)

made = 0
for num, x, y, w, h, lay, net in PADS:
    if not net:
        continue
    # Lay the segment along the pad's LONG axis so it occupies the centreline
    # whichever way the branches approached from.
    if h >= w:
        x0, y0, x1, y1 = x, y - h / 2.0, x, y + h / 2.0
        tw = w
    else:
        x0, y0, x1, y1 = x - w / 2.0, y, x + w / 2.0, y
        tw = h
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(int(round(x0 * S)), int(round(y0 * S))))
    t.SetEnd(pcbnew.VECTOR2I(int(round(x1 * S)), int(round(y1 * S))))
    t.SetWidth(int(round(tw * S)))
    t.SetLayer(lay)
    n = board.FindNet(net)
    if n is None:
        print("   *** net %s not on board" % net)
        continue
    t.SetNet(n)
    board.Add(t)
    made += 1

print("replaced %d pad(s) with centreline copper; footprint removed" % made, flush=True)
pcbnew.SaveBoard(OUT, board)
print("saved %s" % OUT, flush=True)
