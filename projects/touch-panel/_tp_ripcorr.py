"""Rip the broken Group B copper out of the two corridors and re-measure them.

Diagnosis under test.  Group A -- the 595 control/power bus (IO9/IO10/IO11/IO12,
+3V3, 25 of the 59 unconnected entries) -- has essentially no copper and must run
vertically past U1..U4.  Two corridors can carry it:

  west strip          x 90.45..91.75   pinched to 3 lanes at 4 y-values
  under-body channel  x 93.70..96.70   mostly 5-7 lanes, 3 at one 0.25 mm slice

Both are occupied -- and every occupant is a Group B ROW/CSEL net, which is
ITSELF unconnected (`F:ROW9` and `B:ROW1` own the under-body channel at y
190..201; `VIA:ROW1` closes it at y 177; `B:CSEL3` owns the west strip from y 180
to 236).  So the broken group is parked in the only routes the other broken group
can use, and neither can close.

Group B is unconnected, so its copper is not worth defending -- it has to be
re-routed regardless.  This removes, on a scratch board, every track and via in
x 90.40..96.45 / y 166..246 that does not belong to Group A or GND, then
re-measures both corridors with the method from _tp_chan.py.

If the corridors open to >= 4 lanes everywhere, the diagnosis is confirmed and
the route for Group A is a solvable, concrete job.  touch-panel.kicad_pcb is
never touched.

  python _tp_ripcorr.py
"""
import shutil

import pcbnew

SRC = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
DST = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\_ripped.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
CLR, HALF, PITCH, SAFETY = 0.2, 0.1, 0.4, 0.5
EDGE = 89.95
KEEP = {"IO9", "IO10", "IO11", "IO12", "+3V3", "GND"}
RX0, RX1, RY0, RY1 = 90.40, 96.45, 166.0, 246.0

board = pcbnew.LoadBoard(SRC)


def bbox(t):
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        xx, yy = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        return xx - r, xx + r, yy - r, yy + r
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth()) / 2
    return (min(x1, x2) - w, max(x1, x2) + w,
            min(y1, y2) - w, max(y1, y2) + w)


doomed = []
per_net = {}
for t in board.GetTracks():
    net = str(t.GetNetname())
    if net in KEEP:
        continue
    l, r, top, bot = bbox(t)
    if r < RX0 or l > RX1 or bot < RY0 or top > RY1:
        continue
    doomed.append(t)
    per_net[net] = per_net.get(net, 0) + 1

print("=== ripping non-Group-A copper out of x %.2f..%.2f, y %.0f..%.0f ==="
      % (RX0, RX1, RY0, RY1))
for n in sorted(per_net, key=lambda k: -per_net[k]):
    print("   %-14s %3d item(s)" % (n, per_net[n]))
print("   TOTAL %d item(s) removed" % len(doomed))

for t in doomed:
    board.Remove(t)
frozen = doomed          # keep the proxies alive until Save() returns
del doomed

# ---- re-measure both corridors (same method as _tp_chan.py) ----------------
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
    l, r, top, bot = bbox(t)
    obst[k].append((l, r, top, bot, str(t.GetLayerName())[0] + ":" + net))
for fp in board.GetFootprints():
    for p in fp.Pads():
        r = p.GetBoundingBox()
        e = (r.GetLeft() / S, r.GetRight() / S, r.GetTop() / S,
             r.GetBottom() / S, "PAD:%s.%s" % (str(fp.GetReference()),
                                               str(p.GetNumber())))
        for k, lay in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)):
            if p.IsOnLayer(lay):
                obst[k].append(e)


def corridor(xlo, xhi, label):
    rows = []
    y = RY0
    while y <= RY1 + 1e-9:
        tot = 0
        who = []
        for k in ("F", "B"):
            blocked = []
            for (l, r, t, b, lab) in obst[k]:
                if t <= y <= b and r > xlo - 1 and l < xhi + 1:
                    blocked.append((l - CLR - HALF, r + CLR + HALF, lab))
            blocked.sort()
            free, cur = [], xlo
            for (bl, bh, _l) in blocked:
                if bl > cur:
                    free.append((cur, min(bl, xhi)))
                cur = max(cur, bh)
            if cur < xhi:
                free.append((cur, xhi))
            free = [(a, b) for a, b in free if b - a > -1e-9]
            n = sum(int((b - a) / PITCH + 1e-9) + 1 for a, b in free)
            tot += n
            if n <= 1:
                who += [lab for (l, r, t, b, lab) in obst[k]
                        if t <= y <= b and l < xhi + 1 and r > xlo - 1]
        if tot < 4:
            rows.append((round(y, 2), tot, sorted(set(who))))
        y += 0.25
    print("\n=== %s (x %.2f..%.2f) ===" % (label, xlo, xhi))
    if not rows:
        print("   capacity >= 4 lanes at EVERY y.  corridor is open.")
        return True
    print("   %d y-sample(s) below 4 lanes:" % len(rows))
    for (y, tot, who) in rows:
        print("      y %7.2f  %d lane(s)   %s" % (y, tot, " ".join(who)[:70]))
    return False


a = corridor(EDGE + SAFETY + HALF, 91.75 - HALF, "west strip")
b = corridor(94.00, 96.40, "under-body channel")

pcbnew.SaveBoard(DST, board)
shutil.copy(SRC[:-10] + ".kicad_pro", DST[:-10] + ".kicad_pro")
print("\nwrote %s (+ .kicad_pro)" % DST)
print("west strip open: %s   under-body open: %s" % (a, b))
del frozen
