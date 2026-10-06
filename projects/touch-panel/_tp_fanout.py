"""Two things the Group A hand-route needs, and the test of Group B's own wall.

(1) EXACT PAD CENTRES for the five Group A nets.  The hand-route needs the real
    copper the tracks must land on -- U1..U4 pads 11/12/13/14/16, the C1..C4
    +3V3 pads, and whichever J1 pads the four control signals arrive on.  A
    guess of "J1 is at the bottom" is not good enough; this prints it.

(2) GROUP B'S WALL.  Group B is the other 26 unconnected entries: 595 Q pads on
    the EAST column (x 97.67) that must reach the R column at x 101.59 (32 of
    them, plus the keys).  They fan out through x 98.65..101.14 -- the strip east
    of the 595 pad columns.  Group A's fix would free the WEST corridors, but if
    this east strip is itself pinched, Group B cannot close either and the board
    still fails.  So measure it the same way: at each y, how many 0.2 mm tracks
    fit side by side between the east pad column and the R column.

If neither is open the board needs a placement change, not more routing, and
that is the user's call.  touch-panel.kicad_pcb is never touched.

  python _tp_fanout.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
CLR, HALF, PITCH = 0.2, 0.1, 0.4

GROUP_A = ("IO9", "IO10", "IO11", "IO12", "+3V3")

# east pad column of the SOIC-16 reaches x 98.650; R pads start at 101.140
XLO, XHI = 98.95, 100.84
Y0, Y1, STEP = 166.0, 247.0, 0.25

board = pcbnew.LoadBoard(BOARD)

# ---- (1) pads ------------------------------------------------------------
print("=== Group A pads (x < 108) ===")
by_net = {}
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    for p in fp.Pads():
        net = str(p.GetNetname())
        if net not in GROUP_A:
            continue
        q = p.GetBoundingBox()
        cx, cy = TO(p.GetPosition().x), TO(p.GetPosition().y)
        if cx > 108:
            continue
        by_net.setdefault(net, []).append((ref, str(p.GetNumber()), cx, cy,
                                           q.GetLeft() / S, q.GetRight() / S,
                                           q.GetTop() / S, q.GetBottom() / S))
for net in GROUP_A:
    rows = sorted(by_net.get(net, []), key=lambda r: (r[0], r[3]))
    print("\n  -- %s : %d pad(s) --" % (net, len(rows)))
    for (ref, pad, cx, cy, l, r, t, b) in rows:
        print("     %-5s pad %-3s  centre (%8.3f, %8.3f)  x %.3f..%.3f"
              % (ref, pad, cx, cy, l, r))

print("\n=== GND pads on the west/under-body side (Group C targets) ===")
for fp in board.GetFootprints():
    ref = str(fp.GetReference())
    for p in fp.Pads():
        if str(p.GetNetname()) != "GND":
            continue
        cx, cy = TO(p.GetPosition().x), TO(p.GetPosition().y)
        if cx > 100 or not (160 <= cy <= 250):
            continue
        print("     %-5s pad %-3s  centre (%8.3f, %8.3f)" % (ref, str(p.GetNumber()), cx, cy))

# ---- (2) the east fan-out gap -------------------------------------------
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

print("\n=== east fan-out gap x %.2f..%.2f  (Group B's 32 Q outputs) ===" % (XLO, XHI))
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
        for (bl, bh, _l) in blocked:
            if bl > cur:
                free.append((cur, min(bl, XHI)))
            cur = max(cur, bh)
        if cur < XHI:
            free.append((cur, XHI))
        free = [(a, b) for a, b in free if b - a > -1e-9]
        n = sum(int((b - a) / PITCH + 1e-9) + 1 for a, b in free)
        who = sorted({lab for (l, r, t, b, lab) in obst[k]
                      if t <= y <= b and l < XHI + 1 and r > XLO - 1})
        cell.append((n, who))
    rows.append((round(y, 2), cell[0], cell[1]))
    y += STEP

print("  %-14s %4s %4s   who is in the way" % ("y", "F", "B"))
i = 0
while i < len(rows):
    key = (rows[i][1][0], rows[i][2][0], tuple(rows[i][1][1]), tuple(rows[i][2][1]))
    j = i
    while j + 1 < len(rows):
        k2 = (rows[j + 1][1][0], rows[j + 1][2][0],
              tuple(rows[j + 1][1][1]), tuple(rows[j + 1][2][1]))
        if k2 != key:
            break
        j += 1
    ya, yb = rows[i][0], rows[j][0]
    span = "%8.2f    " % ya if ya == yb else "%6.2f-%-6.2f" % (ya, yb)
    who = ""
    if key[0] + key[1] <= 3:
        who = "  " + " ".join(key[2] + key[3])[:60]
    print("  %-14s %4d %4d%s" % (span, key[0], key[1], who))
    i = j + 1

print("\n  worst F.Cu %d   worst B.Cu %d   worst F+B %d"
      % (min(r[1][0] for r in rows), min(r[2][0] for r in rows),
         min(r[1][0] + r[2][0] for r in rows)))
n_q = sum(1 for fp in board.GetFootprints()
          for p in fp.Pads()
          if str(fp.GetReference()) in ("U1", "U2", "U3", "U4")
          and str(p.GetNumber()) in ("1", "2", "3", "4", "5", "6", "7", "15"))
print("  Q outputs that must fan east through it: %d" % n_q)
