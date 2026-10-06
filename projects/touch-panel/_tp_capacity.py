"""True capacity of the west strip, band by band, per layer.

_tp_westband.py and _tp_capsrot.py both asked for an x that is free for the WHOLE
70 mm span of the register column, and both got x 90.55..90.75 -- one lane per
layer.  That is the wrong test.  A track does not have to hold one x for 70 mm:
it can run in one lane through a register body, jog sideways in the 11 mm gap
between two registers, and continue in a different lane.  The gaps exist
precisely to allow that.

So the real question is not "is there a whole-span lane" but "how many lanes are
free in EACH band".  If every band offers >= 3 F.Cu lanes and >= 1 B.Cu lane,
the four control nets (IO10 SRCLK, IO11 RCLK, IO12 /OE, +3V3) can be threaded
through by jogging in the gaps, and the problem is search, not capacity.  If any
band offers 1, that band is a hard bottleneck and the nets must share it in
sequence, which is where a router gives up.

Bands are the four register bodies and the four gaps between/below them, using
the measured pad spans (U1 pads y 168.56..177.44, registers every 20 mm).

  python _tp_capacity.py
"""
from collections import defaultdict

import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6
EDGE = 89.95
EDGE_CLR = 0.5
CLR = 0.2
PITCH = 0.4          # 0.2 track + 0.2 clearance

XLO = EDGE + EDGE_CLR + 0.1      # 90.55
XHI = 91.75 - CLR - 0.1          # 91.45  (595 pad column west edge)

board = pcbnew.LoadBoard(BOARD)

# ---- obstacles, with net names so the blockers can be named ---------------
obst = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        xx, yy = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        obst.append((xx - r, xx + r, yy - r, yy + r, "V", str(t.GetNetname())))
        continue
    if t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = TO(s.x), TO(s.y), TO(e.x), TO(e.y)
    w = TO(t.GetWidth()) / 2
    obst.append((min(x1, x2) - w, max(x1, x2) + w,
                 min(y1, y2) - w, max(y1, y2) + w,
                 "F" if t.GetLayer() == pcbnew.F_Cu else "B",
                 str(t.GetNetname())))
for fp in board.GetFootprints():
    for p in fp.Pads():
        q = p.GetBoundingBox()
        obst.append((q.GetLeft() / S, q.GetRight() / S,
                     q.GetTop() / S, q.GetBottom() / S,
                     "P", str(fp.GetReference())))

BANDS = [("U1 body", 168.56, 177.44), ("gap 1  ", 177.44, 188.56),
         ("U2 body", 188.56, 197.44), ("gap 2  ", 197.44, 208.56),
         ("U3 body", 208.56, 217.44), ("gap 3  ", 217.44, 228.56),
         ("U4 body", 228.56, 237.44), ("below  ", 237.44, 245.00)]


def free_lanes(want, y0, y1):
    """x centres free on `want` for every y in the band, and who blocks them."""
    ok = []
    x = XLO
    while x <= XHI + 1e-9:
        good = True
        y = y0
        while y <= y1 + 1e-9:
            for (l, r, t0, b, tag, net) in obst:
                if tag != want and tag != "V" and tag != "P":
                    continue
                if l - CLR - 0.1 <= x <= r + CLR + 0.1 and \
                   t0 - CLR - 0.1 <= y <= b + CLR + 0.1:
                    good = False
                    break
            if not good:
                break
            y += 0.2
        if good:
            ok.append(round(x, 3))
        x += 0.05
    # merge into runs
    runs = []
    for v in ok:
        if runs and abs(v - runs[-1][1] - 0.05) < 1e-6:
            runs[-1][1] = v
        else:
            runs.append([v, v])
    return runs


print("legal track centres in the strip: x %.2f..%.2f" % (XLO, XHI))
print("\n=== free lanes per band (a lane = x free for every y in the band) ===")
summary = {}
for (name, y0, y1) in BANDS:
    row = {}
    for want, lbl in (("F", "F.Cu"), ("B", "B.Cu")):
        runs = free_lanes(want, y0, y1)
        # a run of width w holds floor(w/PITCH)+1 lanes
        n = sum(int((b - a) / PITCH) + 1 for a, b in runs)
        row[lbl] = (n, runs)
    summary[name] = row
    print("  %s y %6.2f..%-6.2f  F.Cu %d lane(s) %-28s  B.Cu %d lane(s) %s"
          % (name, y0, y1,
             row["F.Cu"][0],
             " ".join("%.2f-%.2f" % (a, b) for a, b in row["F.Cu"][1]) or "-",
             row["B.Cu"][0],
             " ".join("%.2f-%.2f" % (a, b) for a, b in row["B.Cu"][1]) or "-"))

print("\n=== who blocks the strip, per band (westmost copper of each culprit) ===")
for (name, y0, y1) in BANDS:
    hits = defaultdict(lambda: 1e9)
    for (l, r, t0, b, tag, net) in obst:
        if tag not in ("F", "B", "V") or b < y0 or t0 > y1:
            continue
        if l > 91.9:
            continue
        hits["%s:%s" % (tag, net)] = min(hits["%s:%s" % (tag, net)], l)
    s = "  ".join("%s@%.2f" % (k, v) for k, v in sorted(hits.items())
                  if v < 91.9)
    print("  %s %s" % (name, s or "CLEAR"))

print("\n=== verdict ===")
worst = min(summary.items(), key=lambda kv: kv[1]["F.Cu"][0])
print("  tightest band on F.Cu: %s with %d lane(s)"
      % (worst[0], worst[1]["F.Cu"][0]))
fw = [n for n, r in summary.items() if r["F.Cu"][0] >= 3]
bw = [n for n, r in summary.items() if r["B.Cu"][0] >= 1]
print("  bands with >=3 F.Cu lanes: %d/%d  %s" % (len(fw), len(BANDS), fw))
print("  bands with >=1 B.Cu lane : %d/%d  %s" % (len(bw), len(BANDS), bw))
print("  four control nets need 4 lanes to co-exist in any single band.")
