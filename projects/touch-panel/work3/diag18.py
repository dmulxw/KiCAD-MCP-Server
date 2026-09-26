"""Where is the copper of the nets that come up 2-11mm short?

reach2.py says CSEL0/1/2/7/8/9 and +3V3 are unreachable from BOTH headers while
stalling a few millimetres from a legal goal cell.  "A few millimetres" means
the target exists and is nearly in hand -- so the question is only which side of
which obstacle it sits on.  Pure geometry, no A*.
"""
import sys, os, math
sys.path.insert(0, os.getcwd())
import pcbnew

S = 1e6
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
NAMES = ["CSEL0", "CSEL1", "CSEL2", "CSEL7", "CSEL8", "CSEL9", "+3V3",
         "CSEL3", "GND", "COL0", "COL9"]

board = pcbnew.LoadBoard('_rip2.kicad_pcb')
j1a = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1A'][0]
j1b = [fp for fp in board.GetFootprints() if fp.GetReference() == 'J1B'][0]
hdr = {p.m_Uuid.AsString() for p in j1a.Pads()} | \
      {p.m_Uuid.AsString() for p in j1b.Pads()}

allc = list(board.GetTracks()) + [p for fp in board.GetFootprints()
                                  for p in fp.Pads()]

def lay(it):
    ns = [n for n, l in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu))
          if it.IsOnLayer(l)]
    return "".join(ns) or "-"

print("J1A pads x=%.2f  y %.2f..%.2f    J1B pads x=%.2f  y %.2f..%.2f\n"
      % (j1a.GetPosition().x/S,
         j1a.GetPosition().y/S, j1a.GetPosition().y/S + 19*2.54,
         j1b.GetPosition().x/S,
         j1b.GetPosition().y/S, j1b.GetPosition().y/S + 19*2.54))

for name in NAMES:
    mine = [it for it in allc if it.GetNetname() == name
            and it.m_Uuid.AsString() not in hdr]
    if not mine:
        print("%-7s  no copper at all" % name)
        continue
    xs, ys, cnt, padn = [], [], 0, 0
    for it in mine:
        bb = it.GetBoundingBox()
        xs += [bb.GetLeft()/S, bb.GetRight()/S]
        ys += [bb.GetTop()/S, bb.GetBottom()/S]
        if isinstance(it, pcbnew.PCB_VIA):
            cnt += 1
        elif isinstance(it, pcbnew.PCB_TRACK):
            cnt += 1
        else:
            padn += 1
    bx = (min(xs), min(ys), max(xs), max(ys))
    # how far is that bbox from each header's pin column?
    def dx(px):
        return max(bx[0]-px, px-bx[2], 0.0)
    def dy(py0, py1):
        return max(bx[1]-py1, py0-bx[3], 0.0)
    da = math.hypot(dx(j1a.GetPosition().x/S),
                    dy(j1a.GetPosition().y/S, j1a.GetPosition().y/S + 19*2.54))
    db = math.hypot(dx(j1b.GetPosition().x/S),
                    dy(j1b.GetPosition().y/S, j1b.GetPosition().y/S + 19*2.54))
    print("%-7s  %3d trk %3d via %3d pad   bbox x %7.2f..%7.2f  y %7.2f..%7.2f"
          % (name, cnt, sum(1 for it in mine if isinstance(it, pcbnew.PCB_VIA)),
             padn, bx[0], bx[2], bx[1], bx[3]))
    print("         straight-line gap to a header:  J1A %.1fmm   J1B %.1fmm"
          % (da, db))
    # layer split, and the y-band it occupies -- the strip is y > 241.5
    layers = {}
    for it in mine:
        layers[lay(it)] = layers.get(lay(it), 0) + 1
    band = ("bottom strip only" if bx[1] > 241.5 else
            "array interior" if bx[3] <= 241.5 else "spans into the strip")
    print("         layers %s      %s\n" % (layers, band), flush=True)
