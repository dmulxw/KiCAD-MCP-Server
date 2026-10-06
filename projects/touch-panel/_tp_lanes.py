"""Every vertical lane in the 595 half of the board, on both layers.

_tp_westband.py found a clean 0.2 channel at x 90.55..90.75 (free on BOTH layers
for the whole 70 mm register span) and noted the band is 0.9 mm wide but only its
western 0.2 is clear at every y.

But the 595s are SOIC-16 (pad metal 91.75..93.70 west column, 96.69..98.64 east
column), which means x 93.70..96.69 -- *under each body* -- has no pads in it at
all.  If that gap is also clear between the registers, the four control nets
(IO10 SRCLK, IO11 RCLK, IO12 /OE, +3V3) can each get their own F.Cu vertical
there with no vias at all, instead of fighting for two edge channels.

So: for every 0.1 mm x-column from the board edge to the east pad column, what
fraction of the register span Y168..238 is free, per layer.  A column at 100%
is a lane that needs no jogs.

  python _tp_lanes.py
"""
import pcbnew

BOARD = (r"D:\source\repos\KiCad-MCP-Server\projects\touch-panel"
         r"\touch-panel.kicad_pcb")
TO = pcbnew.ToMM
S = 1e6

Y0, Y1 = 168.0, 238.0
EDGE = 89.95
EDGE_CLR = 0.5
CLR = 0.2
REFS = ("U1", "U2", "U3", "U4")

board = pcbnew.LoadBoard(BOARD)

# ---- pad metal extents of the four registers ------------------------------
own = []
for fp in board.GetFootprints():
    if str(fp.GetReference()) in REFS:
        for p in fp.Pads():
            q = p.GetBoundingBox()
            own.append((q.GetLeft() / S, q.GetRight() / S,
                        q.GetTop() / S, q.GetBottom() / S))
xs = sorted(r for a, b, _c, _d in own for r in (a, b))
print("register pad metal columns: %.3f..%.3f  and  %.3f..%.3f"
      % (min(a for a, b, _c, _d in own), max(a for a, b, _c, _d in own), 0, 0))
west = [r for a, b, _c, _d in own if b < 95 for r in (a, b)]
east = [r for a, b, _c, _d in own if a > 95 for r in (a, b)]
print("  west column metal x %.3f..%.3f" % (min(west), max(west)))
print("  east column metal x %.3f..%.3f" % (min(east), max(east)))
GAP0, GAP1 = max(west), min(east)
print("  the under-body gap: x %.3f..%.3f  (%.3f mm)"
      % (GAP0, GAP1, GAP1 - GAP0))

# ---- obstacles -------------------------------------------------------------
obst = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        x, y = TO(q.x), TO(q.y)
        r = TO(t.GetWidth(pcbnew.F_Cu)) / 2
        obst.append((x - r, y - r, x + r, y + r, "V", str(t.GetNetname())))
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
                 max(x1, x2) + w / 2, max(y1, y2) + w / 2, lay,
                 str(t.GetNetname())))

XLO = EDGE + EDGE_CLR + 0.1
XHI = GAP1          # scan out to the east pad column

print("\n=== per 0.1 mm x-column: %% of Y168..238 free (F.Cu / B.Cu) ===")
print("  %-7s %-6s %-6s  %s" % ("x", "F.Cu", "B.Cu", "worst blocker on F.Cu"))
rows = []
k = 0
while True:
    x = round(XLO + k * 0.1, 3)
    if x > XHI + 1e-9:
        break
    hits = {"F": [], "B": []}
    n = 0
    tot = 0
    y = Y0
    while y <= Y1 + 1e-9:
        tot += 1
        ok = {"F": True, "B": True}
        for (l, t0, r, b, tag, net) in obst:
            if tag == "V":
                if l - CLR - 0.1 <= x <= r + CLR + 0.1 and \
                   t0 - CLR - 0.1 <= y <= b + CLR + 0.1:
                    ok["F"] = ok["B"] = False
                    hits["F"].append((net, y))
            else:
                if tag in ("F", "B") and \
                   l - CLR - 0.1 <= x <= r + CLR + 0.1 and \
                   t0 - CLR - 0.1 <= y <= b + CLR + 0.1:
                    ok[tag] = False
                    if tag == "F":
                        hits["F"].append((net, y))
        if ok["F"]:
            n += 1
        y += 0.25
    fp = 100.0 * n / tot
    from collections import Counter
    worst = Counter(nn for nn, _yy in hits["F"]).most_common(2)
    rows.append((x, fp, worst))
    k += 1

for (x, fp, worst) in rows:
    bar = "#" * int(fp / 5)
    print("  %-7.2f %-6.0f%% %-6s  %s"
          % (x, fp, "", " ".join("%s x%d" % w for w in worst)))

print("\n=== columns at 100%% on F.Cu, contiguous runs ===")
good = [x for (x, fp, _w) in rows if fp >= 99.9]
if not good:
    print("  none")
else:
    run = [good[0]]
    for x in good[1:]:
        if abs(x - run[-1] - 0.1) < 1e-6:
            run.append(x)
        else:
            print("  x %.2f..%.2f  (%d columns, %.2f mm)"
                  % (run[0], run[-1], len(run), run[-1] - run[0] + 0.2))
            run = [x]
    print("  x %.2f..%.2f  (%d columns, %.2f mm)"
          % (run[0], run[-1], len(run), run[-1] - run[0] + 0.2))
