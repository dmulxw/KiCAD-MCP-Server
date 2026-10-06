"""Is the channel UNDER the four 595 bodies the corridor the board is missing?

Each SOIC-16 in SOIC-16_3.9x9.9mm_P1.27mm has its two pad columns 3.00 mm apart:
west pads span x 91.750..93.700, east pads x 96.700..98.650, so there is a
3.000 mm strip x 93.700..96.700 with no pad copper at all.  That strip runs the
whole 69 mm of the register column (y 168.56..237.44), unbroken by the 11 mm
gaps between parts.

It matters because it touches BOTH pad columns.  A west pad's copper reaches
1..93.700 -- exactly this strip's west edge -- so a track in the strip needs no
run down the west corridor at all: it goes up the strip, and turns west 0.3 mm
at the pad row it wants.  That is true for all 32 west pads of U1..U4, which is
every control pin (11 SRCLK, 12 RCLK, 13 /OE, 14 DS, 15 Q7, 10 /MR, 16 VCC).

_tp_chan.py measured the west corridor at x 90.45..91.65 and found it pinched to
3 usable lanes where 4 signals are needed.  If this strip is open, the west
corridor stops being the only route and the whole framing changes.

Same y-profile method: at each y, count the 0.2 mm tracks that fit side by side.
The corridor's capacity is the minimum of that count over y.

  python _tp_underbody.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
CLR = 0.2
HALF = 0.1
PITCH = 0.4

# inside the body, with a 0.1 copper half-width and 0.2 clearance to both pad
# columns: 93.700 + 0.1 + 0.2 = 94.00 .. 96.700 - 0.1 - 0.2 = 96.40
XLO, XHI = 94.00, 96.40
Y0, Y1, STEP = 166.0, 247.0, 0.25

board = pcbnew.LoadBoard(BOARD)

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
        e = (r.GetLeft() / S, r.GetRight() / S,
             r.GetTop() / S, r.GetBottom() / S, "PAD:%s.%s" % (ref, str(p.GetNumber())))
        for k, lay in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)):
            if p.IsOnLayer(lay):
                obst[k].append(e)

print("channel under the 595 bodies: x %.2f..%.2f (%d lanes at %.1f pitch)"
      % (XLO, XHI, int((XHI - XLO) / PITCH) + 1, PITCH))

rows = []
y = Y0
while y <= Y1 + 1e-9:
    cell = []
    for k in ("F", "B"):
        blocked = []
        for (l, r, t, b, lab) in obst[k]:
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
        free = [(a, b) for a, b in free if b - a > -1e-9]
        lanes = sum(int((b - a) / PITCH + 1e-9) + 1 for a, b in free)
        who = sorted({lab for (l, r, t, b, lab) in obst[k]
                      if t <= y <= b and l < XHI + 1 and r > XLO - 1})
        cell.append((lanes, free, who))
    rows.append((round(y, 2), cell[0], cell[1]))
    y += STEP

print("\n=== y-profile of the under-body channel ===")
print("  %-14s %4s %4s   who is in the way (x range on that layer)" % ("y", "F", "B"))
i, out = 0, []
while i < len(rows):
    key = (rows[i][1][0], rows[i][2][0], tuple(rows[i][1][2]),
           tuple(rows[i][2][2]))
    j = i
    while j + 1 < len(rows):
        k2 = (rows[j + 1][1][0], rows[j + 1][2][0],
              tuple(rows[j + 1][1][2]), tuple(rows[j + 1][2][2]))
        if k2 != key:
            break
        j += 1
    ya, yb = rows[i][0], rows[j][0]
    f_n, b_n = key[0], key[1]
    span = "%8.2f    " % ya if ya == yb else "%6.2f-%-6.2f" % (ya, yb)
    who = ""
    if f_n < 4 or b_n < 4:
        who = "  " + " ".join(key[2] + key[3])[:64]
    print("  %-14s %4d %4d%s" % (span, f_n, b_n, who))
    out.append((ya, yb, f_n, b_n))
    i = j + 1

mnF = min(r[1][0] for r in rows)
mnB = min(r[2][0] for r in rows)
mnT = min(r[1][0] + r[2][0] for r in rows)
print("\n  worst F.Cu  : %d lane(s)" % mnF)
print("  worst B.Cu  : %d lane(s)" % mnB)
print("  worst F+B   : %d lane(s)   <-- the corridor's real capacity" % mnT)

# where are the pinches?
print("\n=== the pinches, and what causes them ===")
for (y, f, b) in rows:
    if f[0] + b[0] >= mnT:
        continue
    print("  y %.2f  F=%d %s  B=%d %s"
          % (y, f[0], f[2] or "-", b[0], b[2] or "-"))
