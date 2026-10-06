"""Is there a vertical lane west of the 595 control column?

The four shift registers put every control pin on one column at x=92.72, pad
pitch 1.27 mm, registers stacked at y 168.56 / 188.56 / 208.56 / 228.56 (SOIC-16,
so the column runs y 168.56 .. 237.44).  IO10, IO11, IO12 and IO9 have ZERO
tracks and +3V3 has only 11 partial ones -- these are the signals that used to
arrive over J8/J10 when the 595s sat on the carrier.

So four nets need a vertical trunk in the strip between the board edge and the
pad column.  This measures whether that strip can hold them.

The strip: board left edge is x 89.95 and min_copper_edge_clearance is 0.5, so
copper starts at 90.45; pad metal starts at x = 92.72 - pad_half.  Sweeping y and
recording which x are free gives the lane set -- if any x is free for the whole
run, a trunk fits there and the job is a straight run plus four stubs per net.

  python _tp_westband.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6

Y0, Y1 = 168.0, 238.0          # the register column, with a little margin
EDGE = 89.95                   # board outline left edge
EDGE_CLR = 0.5                 # min_copper_edge_clearance from the .kicad_pro
CLR = 0.2                      # Default net class clearance
STEP = 0.05

board = pcbnew.LoadBoard(BOARD)

# ---- the pad column: where pad metal actually starts -----------------------
regs = [fp for fp in board.GetFootprints()
        if str(fp.GetReference()) in ("U1", "U2", "U3", "U4")]
padspan = []
for fp in regs:
    for p in fp.Pads():
        if abs(p.GetPosition().x / S - 92.72) < 0.01:
            q = p.GetBoundingBox()
            padspan.append((q.GetLeft() / S, q.GetRight() / S))
PLO = min(a for a, _ in padspan)
PHI = max(b for _, b in padspan)
print("pad column at x=92.72: pad metal x %.3f..%.3f  (%d pads)"
      % (PLO, PHI, len(padspan)))
XLO = EDGE + EDGE_CLR + 0.1     # westernmost legal track CENTRE
XHI = PLO - CLR - 0.1           # easternmost legal track CENTRE
print("legal track centre band: x %.3f .. %.3f  (%.3f mm)"
      % (XLO, XHI, XHI - XLO))

# ---- obstacles as boxes, tagged with the layer they block ------------------
obst = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        x, y = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        obst.append((x - r, y - r, x + r, y + r, "V"))
        continue
    if not isinstance(t, pcbnew.PCB_TRACK):
        continue
    if t.GetLayer() == pcbnew.F_Cu:
        lay = "F"
    elif t.GetLayer() == pcbnew.B_Cu:
        lay = "B"
    else:
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth())
    obst.append((min(x1, x2) - w / 2, min(y1, y2) - w / 2,
                 max(x1, x2) + w / 2, max(y1, y2) + w / 2, lay))
for fp in regs:
    for p in fp.Pads():
        q = p.GetBoundingBox()
        obst.append((q.GetLeft() / S, q.GetTop() / S, q.GetRight() / S,
                     q.GetBottom() / S, "P"))

# ---- who blocks the band, ignoring the register pads themselves ------------
print("\n=== what occupies the band x %.2f..%.2f (excluding the U1-U4 pads) ===" % (XLO - 0.2, XHI + 0.5))
from collections import Counter
who = Counter()
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        x, y = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        if XHI + 0.5 < x - r or x + r < XLO - 0.2:
            continue
        if y + r < Y0 or y - r > Y1:
            continue
        who["VIA:" + str(t.GetNetname())] += 1
        continue
    if not isinstance(t, pcbnew.PCB_TRACK):
        continue
    if t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth())
    if XHI + 0.5 < min(x1, x2) - w / 2 or max(x1, x2) + w / 2 < XLO - 0.2:
        continue
    if max(y1, y2) + w / 2 < Y0 or min(y1, y2) - w / 2 > Y1:
        continue
    lay = "F" if t.GetLayer() == pcbnew.F_Cu else "B"
    who[lay + ":" + str(t.GetNetname())] += 1
for k, v in who.most_common():
    print("   %-14s %3d" % (k, v))


# ---- a point is free if no obstacle of the same layer is within CLR --------
def blocked(x, y, want):
    for (l, t0, r, b, tag) in obst:
        if tag in ("V", "P"):
            if l - CLR - 0.1 <= x <= r + CLR + 0.1 and \
               t0 - CLR - 0.1 <= y <= b + CLR + 0.1:
                return tag
        elif tag == want:
            if l - CLR - 0.1 <= x <= r + CLR + 0.1 and \
               t0 - CLR - 0.1 <= y <= b + CLR + 0.1:
                return tag
    return None


def lane_set(want):
    """x values free at every y across the span, on the given layer."""
    common = None
    y = Y0
    while y <= Y1 + 1e-9:
        xs = set()
        k = 0
        while True:
            x = round(XLO + k * STEP, 3)
            if x > XHI + 1e-9:
                break
            if blocked(x, y, want) is None:
                xs.add(x)
            k += 1
        common = xs if common is None else (common & xs)
        if not common:
            return y, set()
        y += 0.25
    return None, common


for want in ("F", "B"):
    ydie, common = lane_set(want)
    lbl = "F.Cu" if want == "F" else "B.Cu"
    if common:
        print("\n%s: %d x hold for the whole span Y%.0f..%.0f -- %s"
              % (lbl, len(common), Y0, Y1, sorted(common)[:24]))
    else:
        print("\n%s: NO x free for the whole span (lane set emptied at y=%.2f)"
              % (lbl, ydie))
