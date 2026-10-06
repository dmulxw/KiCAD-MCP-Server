"""Channel capacity of the west corridor, y by y -- the decisive measurement.

_tp_capacity.py gave the per-band picture but used a conservative margin and a
coarse run merge, so its lane COUNT is unreliable (float slop of +-1).  The runs
it printed are the trustworthy part, and they say every inter-register gap
pinches the corridor to a single 0.35 mm run on F.Cu and one on B.Cu.

That is still not the answer, because a run of legal centres holds as many
tracks as fit side by side, and a track only has to hold its x where it is
actually pinched -- it may jog sideways anywhere there is horizontal room.

What settles it is the y-profile: at each y, count how many 0.2 mm tracks can
sit side by side in the corridor, on each layer.  A vertical bus of k nets
crosses every y in the corridor, so the capacity of the corridor is the MINIMUM
of that count over y.  That minimum is the number, and it cannot be talked
around.

Two profiles are printed: as the board stands, and with CSEL3's copper removed.
CSEL3 is a Group B net that is itself unconnected, and it owns B:CSEL3@91.05 in
every band from gap 1 to U4 -- so a broken net may be squatting on the corridor
the control bus needs.  The second profile prices that.

  python _tp_chan.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
EDGE = 89.95
CLR = 0.2
SAFETY = 0.5          # min_copper_edge_clearance
HALF = 0.1            # half of a 0.2 mm track
PITCH = 0.4           # 0.2 track + 0.2 clearance
XLO = EDGE + SAFETY + HALF          # 90.55
XHI = 91.75 - HALF                  # 91.65
Y0, Y1, STEP = 166.0, 246.0, 0.25

board = pcbnew.LoadBoard(BOARD)

# per-layer obstacle list: (x_lo, x_hi, y_lo, y_hi, label)
obst = {"F": [], "B": []}
for t in board.GetTracks():
    net = str(t.GetNetname())
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        xx, yy = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        for k in ("F", "B"):
            obst[k].append((xx - r, xx + r, yy - r, yy + r, "VIA:" + net))
        continue
    if t.GetLayer() == pcbnew.F_Cu:
        k = "F"
    elif t.GetLayer() == pcbnew.B_Cu:
        k = "B"
    else:
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth()) / 2
    obst[k].append((min(x1, x2) - w, max(x1, x2) + w,
                    min(y1, y2) - w, max(y1, y2) + w,
                    str(t.GetLayerName())[0] + ":" + net))
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    for p in fp.Pads():
        r = p.GetBoundingBox()
        e = (r.GetLeft() / S, r.GetRight() / S, r.GetTop() / S, r.GetBottom() / S,
             "PAD:%s.%s" % (ref, str(p.GetNumber())))
        for k, lay in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)):
            if p.IsOnLayer(lay):
                obst[k].append(e)


def profile(drop=None):
    """Run-length-encoded (F lanes, B lanes, blockers) over the corridor."""
    rows = []
    y = Y0
    while y <= Y1 + 1e-9:
        cell = []
        for k in ("F", "B"):
            blocked = []
            for (l, r, t, b, lab) in obst[k]:
                if drop and drop in lab:
                    continue
                if t <= y <= b and r > XLO - 1 and l < XHI + 1:
                    blocked.append((l - CLR - HALF, r + CLR + HALF, lab))
            blocked.sort()
            free, cur = [], XLO
            for (bl, bh, _lab) in blocked:
                if bl > cur:
                    free.append((cur, min(bl, XHI)))
                cur = max(cur, bh)
            if cur < XHI:
                free.append((cur, XHI))
            free = [(a, b) for a, b in free if b - a >= -1e-9]
            lanes = sum(int((b - a) / PITCH + 1e-9) + 1 for a, b in free)
            cell.append((lanes, free,
                         sorted({lab for (_l, _r, lab) in
                                 [(l, r, lab) for (l, r, t, b, lab) in obst[k]
                                  if (drop or "") not in lab and t <= y <= b
                                  and l < XHI + 1 and r > XLO - 1]})))
        rows.append((round(y, 2), cell[0], cell[1]))
        y += STEP
    return rows


def rle(rows):
    out = []
    for (y, f, b) in rows:
        key = (f[0], b[0], tuple(f[2]), tuple(b[2]))
        if out and out[-1][2] == key:
            out[-1][1] = y
        else:
            out.append([y, y, key])
    return out


for drop, title in ((None, "AS THE BOARD STANDS"),
                    ("CSEL3", "WITH CSEL3'S COPPER REMOVED (hypothetical)")):
    rows = profile(drop)
    print("=" * 78)
    print("%s -- corridor x %.2f..%.2f" % (title, XLO, XHI))
    print("=" * 78)
    print("  %-14s %4s %4s   blockers at the low point" % ("y", "F", "B"))
    for (ya, yb, key) in rle(rows):
        f_n, b_n, f_bl, b_bl = key[0], key[1], key[2], key[3]
        if ya == yb:
            span = "%8.2f    " % ya
        else:
            span = "%6.1f-%-6.1f" % (ya, yb)
        note = ""
        if f_n + b_n <= 3:
            note = "  tight: " + " ".join(
                sorted(set(list(f_bl) + list(b_bl)))[:6])
        print("  %-14s %4d %4d%s" % (span, f_n, b_n, note))
    mn = min(min(r[1][0], r[2][0]) for r in rows)
    print("  --> corridor capacity = %d lane(s) at the pinch "
          "(min over y of min(F,B))" % mn)
    tot = [min(r[1][0], r[2][0]) + max(r[1][0], r[2][0]) for r in rows]
    print("  --> best simultaneous total on the two layers = %d" % max(tot))
    print()

print("Four signals must each run the corridor end to end:")
print("  IO10 SRCLK -> pads 11 of U1..U4   (y 171.10 .. 231.10)")
print("  IO11 RCLK  -> pads 12 of U1..U4   (y 172.37 .. 232.37)")
print("  IO12 /OE   -> pads 13 of U1..U4   (y 173.64 .. 233.64)")
print("  +3V3       -> pads 10/16 of U1..U4, plus C1..C4 pad 1")
