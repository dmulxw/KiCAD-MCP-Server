"""Three checks before committing to a hand-route of the Group A bus.

(1) PER-LAYER lanes on the ripped board.  _tp_ripcorr.py reported "capacity >= 4
    lanes at EVERY y" but that number is F+B COMBINED -- it would also pass on
    F=4/B=0.  The routing plan needs one F lane AND one B lane in each corridor
    (one net per layer per corridor, so that a net's east-west taps never cross
    a same-layer vertical).  So measure min(F) and min(B) separately.

(2) WHERE THE CONTROL SIGNALS COME IN.  IO9/IO10/IO11/IO12 each show only ONE
    pad inside x < 108 (U1..U4 pin 11/12/13/14).  The other end is off to the
    east, so the bus has to start there.  Print every pad of those nets.

(3) THE +3V3 TIE-IN.  Whether +3V3 already has copper near the register column,
    or whether it too has to be brought in from the east.

  python _tp_verify.py
"""
import pcbnew

RIP = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\_ripped.kicad_pcb")
SRC = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
       r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
CLR, HALF, PITCH = 0.2, 0.1, 0.4
Y0, Y1, STEP = 166.0, 246.0, 0.25
CORR = [(90.55, 91.65, "west strip"), (94.00, 96.40, "under-body channel")]


def obstacles(board):
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
            e = (r.GetLeft() / S, r.GetRight() / S, r.GetTop() / S,
                 r.GetBottom() / S, "PAD:%s.%s" % (ref, str(p.GetNumber())))
            for k, lay in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)):
                if p.IsOnLayer(lay):
                    obst[k].append(e)
    return obst


def lanes(obst, k, y, xlo, xhi):
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
    return (sum(int((b - a) / PITCH + 1e-9) + 1 for a, b in free), free)


print("=" * 74)
print("(1) per-layer lanes on _ripped.kicad_pcb")
print("=" * 74)
rb = pcbnew.LoadBoard(RIP)
ro = obstacles(rb)
for (xlo, xhi, name) in CORR:
    wf = wb = 99
    ywf = ywb = 0.0
    for i in range(int((Y1 - Y0) / STEP) + 1):
        y = Y0 + i * STEP
        nf, _ = lanes(ro, "F", y, xlo, xhi)
        nb, _ = lanes(ro, "B", y, xlo, xhi)
        if nf < wf:
            wf, ywf = nf, y
        if nb < wb:
            wb, ywb = nb, y
    print("  %-20s worst F = %d lane(s) @ y %.2f   worst B = %d lane(s) @ y %.2f"
          % (name, wf, ywf, wb, ywb))
    print("     -> one F vertical + one B vertical %s"
          % ("FITS" if (wf >= 1 and wb >= 1) else "DOES NOT FIT"))

print()
print("=" * 74)
print("(2) every pad on the four control nets, whole board")
print("=" * 74)
sb = pcbnew.LoadBoard(SRC)
for net in ("IO9", "IO10", "IO11", "IO12"):
    rows = []
    for fp in sb.GetFootprints():
        for p in fp.Pads():
            if str(p.GetNetname()) != net:
                continue
            cx, cy = TO(p.GetPosition().x), TO(p.GetPosition().y)
            rows.append((cx, cy, str(fp.GetReference()), str(p.GetNumber())))
    rows.sort()
    print("  %-6s %d pad(s):" % (net, len(rows)))
    for (cx, cy, ref, pad) in rows:
        print("        %-6s pad %-4s (%8.3f, %8.3f)" % (ref, pad, cx, cy))

print()
print("=" * 74)
print("(3) +3V3 copper near the register column / tie-in points")
print("=" * 74)
seg = {"F": 0, "B": 0}
vias = 0
xmin, xmax, ymin, ymax = 1e9, -1e9, 1e9, -1e9
near = []
for t in sb.GetTracks():
    if str(t.GetNetname()) != "+3V3":
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        xx, yy = TO(q.x), TO(q.y)
        vias += 1
        xmin, xmax = min(xmin, xx), max(xmax, xx)
        ymin, ymax = min(ymin, yy), max(ymax, yy)
        if xx < 112:
            near.append(("VIA", xx, yy))
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    if t.GetLayer() == pcbnew.F_Cu:
        seg["F"] += 1
    elif t.GetLayer() == pcbnew.B_Cu:
        seg["B"] += 1
    else:
        continue
    xmin, xmax = min(xmin, x1, x2), max(xmax, x1, x2)
    ymin, ymax = min(ymin, y1, y2), max(ymax, y1, y2)
    if min(x1, x2) < 112:
        near.append(("SEG", x1, y1, x2, y2, str(t.GetLayerName())))
print("  whole net: F.Cu %d seg, B.Cu %d seg, %d via(s), bbox x %.1f..%.1f y %.1f..%.1f"
      % (seg["F"], seg["B"], vias, xmin, xmax, ymin, ymax))
print("  items west of x 112 (%d):" % len(near))
for it in near[:25]:
    print("     ", it)
print("\n  -- other pads on +3V3 outside the register column --")
seen = 0
for fp in sb.GetFootprints():
    for p in fp.Pads():
        if str(p.GetNetname()) != "+3V3":
            continue
        cx, cy = TO(p.GetPosition().x), TO(p.GetPosition().y)
        if cx < 108:
            continue
        print("     %-6s pad %-4s (%8.3f, %8.3f)"
              % (str(fp.GetReference()), str(p.GetNumber()), cx, cy))
        seen += 1
        if seen > 24:
            break
    if seen > 24:
        break
print("     (showing first %d)" % min(seen, 25))
